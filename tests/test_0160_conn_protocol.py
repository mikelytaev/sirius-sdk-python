import json

import pytest

from sirius_sdk import Agent, Pairwise
from sirius_sdk.agent.aries_rfc.feature_0160_connection_protocol import *

from .helpers import run_coroutines, IndyAgent


async def read_events(agent: Agent):
    listener = await agent.subscribe()
    async for event in listener:
        print('========= EVENT ============')
        print(json.dumps(event, indent=2, sort_keys=True))
        print('============================')


async def run_inviter(agent: Agent, expected_connection_key: str, me: Pairwise.Me=None):
    my_endpoint = [e for e in agent.endpoints if e.routing_keys == []][0]
    listener = await agent.subscribe()
    async for event in listener:
        connection_key = event['recipient_verkey']
        if expected_connection_key == connection_key:
            request = event['message']
            assert isinstance(request, ConnRequest)
            # Setup state machine
            machine = Inviter(agent)
            if me is None:
                my_did, my_verkey = await agent.wallet.did.create_and_store_my_did()
                me = Pairwise.Me(did=my_did, verkey=my_verkey)
            # create connection
            ok, pairwise = await machine.create_connection(me, connection_key, request, my_endpoint)
            assert ok is True
            if await agent.wallet.pairwise.is_pairwise_exists(pairwise.their.did):
                await agent.wallet.pairwise.set_pairwise_metadata(
                    their_did=pairwise.their.did,
                    metadata=pairwise.metadata
                )
            else:
                await agent.wallet.pairwise.create_pairwise(
                    their_did=pairwise.their.did,
                    my_did=pairwise.me.did,
                    metadata=pairwise.metadata
                )
    pass


async def run_invitee(agent: Agent, invitation: Invitation, my_label: str, me: Pairwise.Me=None):
    if me is None:
        my_did, my_verkey = await agent.wallet.did.create_and_store_my_did()
        me = Pairwise.Me(did=my_did, verkey=my_verkey)
    my_endpoint = [e for e in agent.endpoints if e.routing_keys == []][0]
    # Create and start machine
    machine = Invitee(agent)
    ok, pairwise = await machine.create_connection(
        me=me, invitation=invitation, my_label=my_label, my_endpoint=my_endpoint
    )
    assert ok is True
    if await agent.wallet.pairwise.is_pairwise_exists(pairwise.their.did):
        await agent.wallet.pairwise.set_pairwise_metadata(
            their_did=pairwise.their.did,
            metadata=pairwise.metadata
        )
    else:
        await agent.wallet.pairwise.create_pairwise(
            their_did=pairwise.their.did,
            my_did=pairwise.me.did,
            metadata=pairwise.metadata
        )


@pytest.mark.asyncio
async def test_establish_connection(agent1: Agent, agent2: Agent):
    inviter = agent1
    invitee = agent2
    await inviter.open()
    await invitee.open()
    try:
        # Get endpoints
        inviter_endpoint_address = [e for e in inviter.endpoints if e.routing_keys == []][0].address
        connection_key = await inviter.wallet.crypto.create_key()
        invitation = Invitation(label='Inviter', endpoint=inviter_endpoint_address, recipient_keys=[connection_key])
        # Init Me
        did, verkey = await inviter.wallet.did.create_and_store_my_did()
        inviter_me = Pairwise.Me(did, verkey)
        did, verkey = await invitee.wallet.did.create_and_store_my_did()
        invitee_me = Pairwise.Me(did, verkey)

        await run_coroutines(
            run_inviter(inviter, connection_key, inviter_me),
            run_invitee(invitee, invitation, 'Invitee', invitee_me)
        )

        # Check for Inviter
        pairwise = await inviter.wallet.pairwise.get_pairwise(invitee_me.did)
        assert pairwise['my_did'] == inviter_me.did
        # Check for Invitee
        pairwise = await invitee.wallet.pairwise.get_pairwise(inviter_me.did)
        assert pairwise['my_did'] == invitee_me.did

    finally:
        await inviter.close()
        await invitee.close()


@pytest.mark.asyncio
async def test_update_pairwise_metadata(agent1: Agent, agent2: Agent):
    inviter = agent1
    invitee = agent2
    await inviter.open()
    await invitee.open()
    try:
        # Init Me
        did, verkey = await inviter.wallet.did.create_and_store_my_did()
        inviter_side = Pairwise.Me(did, verkey)
        did, verkey = await invitee.wallet.did.create_and_store_my_did()
        invitee_side = Pairwise.Me(did, verkey)
        # Manually set pairwise list
        await inviter.wallet.did.store_their_did(invitee_side.did, invitee_side.verkey)
        await invitee.wallet.did.store_their_did(inviter_side.did, inviter_side.verkey)
        await inviter.wallet.pairwise.create_pairwise(
            their_did=invitee_side.did,
            my_did=inviter_side.did
        )
        await invitee.wallet.pairwise.create_pairwise(
            their_did=inviter_side.did,
            my_did=invitee_side.did
        )

        # Run
        inviter_endpoint_address = [e for e in inviter.endpoints if e.routing_keys == []][0].address
        connection_key = await inviter.wallet.crypto.create_key()
        invitation = Invitation(label='Inviter', endpoint=inviter_endpoint_address, recipient_keys=[connection_key])

        await run_coroutines(
            run_inviter(inviter, connection_key, inviter_side),
            run_invitee(invitee, invitation, 'Invitee', invitee_side)
        )

        # Check for Inviter
        pairwise = await inviter.wallet.pairwise.get_pairwise(invitee_side.did)
        assert pairwise['metadata'] != {}

        # Check for Invitee
        pairwise = await invitee.wallet.pairwise.get_pairwise(inviter_side.did)
        assert pairwise['metadata'] != {}

    finally:
        await inviter.close()
        await invitee.close()


@pytest.mark.asyncio
async def test_invitee_back_compatibility(indy_agent: IndyAgent, agent1: Agent):
    their_invitaton = await indy_agent.create_invitation(label='Test Invitee')
    invitation = Invitation.from_url(their_invitaton['url'])
    inviter = agent1
    await inviter.open()
    try:
        my_did, my_verkey = await agent1.wallet.did.create_and_store_my_did()
        me = Pairwise.Me(did=my_did, verkey=my_verkey)
        await run_coroutines(
            run_invitee(agent1, invitation, 'Invitee', me),
            read_events(agent1)
        )
        invitation_pairwise = None
        for pairwise in await agent1.wallet.pairwise.list_pairwise():
            if pairwise['my_did'] == my_did:
                invitation_pairwise = pairwise
                break
        assert invitation_pairwise is not None
    finally:
        await inviter.close()


@pytest.mark.asyncio
async def test_inviter_back_compatibility(indy_agent: IndyAgent, agent1: Agent):
    await agent1.open()
    try:
        # Get endpoints
        my_endpoint_address = [e for e in agent1.endpoints if e.routing_keys == []][0].address
        connection_key = await agent1.wallet.crypto.create_key()
        my_invitation = Invitation(label='Inviter', endpoint=my_endpoint_address, recipient_keys=[connection_key])
        url = my_invitation.invitation_url
        my_did, my_verkey = await agent1.wallet.did.create_and_store_my_did()
        me = Pairwise.Me(did=my_did, verkey=my_verkey)
        await run_coroutines(
            run_inviter(agent1, connection_key, me),
            indy_agent.invite(invitation_url=url),
        )
        invitated_pairwise = None
        for pairwise in await agent1.wallet.pairwise.list_pairwise():
            if pairwise['my_did'] == my_did:
                invitated_pairwise = pairwise
                break
        assert invitated_pairwise is not None
    finally:
        await agent1.cl