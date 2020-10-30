import os
import sys
import json
import uuid
import random
import asyncio
from enum import Enum
from typing import Optional

import sirius_sdk
from sirius_sdk.base import AbstractStateMachine
from sirius_sdk.messaging import Message

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from consts import *


BANK = AGENT2
EMPLOYER = AGENT1
DID_EMPLOYER = 'Th7MpTaRZVRYnPiabds81Y'
VERKEY_EMPLOYER = 'FYmoFw55GeQH7SRFa37dkx1d2dZ3zUF8ckg7wmL7ofN4'
DID_BANK = 'T8MtAB98aCkgNLtNfQx6WG'
VERKEY_BANK = 'FEvX3nsJ8VjW4qQv4Dh9E3NDEx1bUPDtc9vkaaoKVyz1'
CONN_KEY_BANK = 'Hoq65QDfJZ1G4qUHXMPkmXcA51ztaQsVTEHN8rZFpWjv'
CONN_KEY_EMPLOYER = 'X3huyDF8TmcRr2hRzmyaQH6rqzjFdNy557FBxVXJDpPV4'
DEMO_SALARY = 3000
DEMO_CURRENCY = 'USD'


def log(message: str):
    print(f'\t{message}')


async def setup_employer_cred_defs(network_name: str = 'test_network'):
    async with sirius_sdk.context(**EMPLOYER):
        dkms = await sirius_sdk.ledger(network_name)  # Test network is prepared for Demo purposes
        schema_id, anon_schema = await sirius_sdk.AnonCreds.issuer_create_schema(
            DID_EMPLOYER, 'demo_salary', '1.0', ['salary', 'currency']
        )
        # Ensure schema exists on DKMS
        schema_ = await dkms.ensure_schema_exists(anon_schema, DID_EMPLOYER)
        # Ensure CredDefs is stored to DKMS
        cred_def_fetched = await dkms.fetch_cred_defs(tag='TAG', schema_id=schema_.id)
        if cred_def_fetched:
            cred_def_ = cred_def_fetched[0]
        else:
            ok, cred_def_ = await dkms.register_cred_def(
                cred_def=sirius_sdk.CredentialDefinition(tag='TAG', schema=schema_),
                submitter_did=DID_EMPLOYER
            )
            assert ok is True
        print('===========================')
        print('cred def ID: ' + cred_def_.id)
        print('===========================')
    return schema_, cred_def_


async def generate_invitations_qr_codes() -> (str, str):
    # BANK
    async with sirius_sdk.context(**BANK):
        try:
            connection_key = await sirius_sdk.Crypto.create_key(seed='0000000000000000SIRIUS_BANK_CONN')
        except sirius_sdk.indy_exceptions.WalletItemAlreadyExists:
            log(f'Bank: conn key {CONN_KEY_BANK} already exists')
        else:
            log(f'Bank: conn key {connection_key} was created')
            assert connection_key == CONN_KEY_BANK
        endpoints = await sirius_sdk.endpoints()
        simple_endpoint = [e for e in endpoints if e.routing_keys == []][0]
        bank_invitation = sirius_sdk.aries_rfc.Invitation(
            label='Sirius Demo bank',
            recipient_keys=[CONN_KEY_BANK],
            endpoint=simple_endpoint.address,
            did=DID_BANK
        )
        log('Bank: invitation')
        log(json.dumps(bank_invitation, indent=2, sort_keys=True))

        # Sirius SDK provide method to generate URL for QR
        # bank_qr_url = await sirius_sdk.generate_qr_code(bank_invitation.invitation_url)

    # EMPLOYER
    async with sirius_sdk.context(**EMPLOYER):
        try:
            connection_key = await sirius_sdk.Crypto.create_key(seed='000000000000SIRIUS_EMPLOYER_CONN')
        except sirius_sdk.indy_exceptions.WalletItemAlreadyExists:
            log(f'Employer: conn key {CONN_KEY_BANK} already exists')
        else:
            log(f'Employer: conn key {connection_key} was created')
            assert connection_key == CONN_KEY_BANK
        endpoints = await sirius_sdk.endpoints()
        simple_endpoint = [e for e in endpoints if e.routing_keys == []][0]
        employer_invitation = sirius_sdk.aries_rfc.Invitation(
            label='Sirius Demo employer',
            recipient_keys=[CONN_KEY_EMPLOYER],
            endpoint=simple_endpoint.address,
            did=DID_EMPLOYER
        )
        log('Employer: invitation')
        log(json.dumps(bank_invitation, indent=2, sort_keys=True))

        # Sirius SDK provide method to generate URL for QR
        # employer_qr_url = await sirius_sdk.generate_qr_code(employer_invitation.invitation_url)

    return 'https://socialsirius.com' + bank_invitation.invitation_url, \
           'https://socialsirius.com' + employer_invitation.invitation_url


async def sirius_bank(network_name: str = 'test_network'):
    async with sirius_sdk.context(**BANK):
        listener = await sirius_sdk.subscribe()
        endpoints = await sirius_sdk.endpoints()
        my_endpoint = [e for e in endpoints if e.routing_keys == []][0]
        dkms = await sirius_sdk.ledger(network_name)
        log('Bank: start to listen events')
        async for event in listener:
            if isinstance(event.message, sirius_sdk.aries_rfc.ConnRequest):
                # Restore invitation request through invitation.connection_key
                # You may use this snippet to encrypt to invitation cookie values for example
                # to link device to browser Web Page
                if event.recipient_verkey == CONN_KEY_BANK:
                    pairwise: Optional[sirius_sdk.Pairwise] = event.pairwise
                    log('Bank: received connection request with connection_key: {CONN_KEY_BANK}')
                    if pairwise is None:
                        log('Bank: unknown participant. Establish new pairwise P2P')
                        try:
                            conn_request: sirius_sdk.aries_rfc.ConnRequest = event.message
                            feature_0160 = sirius_sdk.aries_rfc.Inviter(
                                me=sirius_sdk.Pairwise.Me(DID_BANK, VERKEY_BANK),  # Public DID
                                connection_key=event.recipient_verkey,
                                my_endpoint=my_endpoint,
                            )
                            success, pairwise = await feature_0160.create_connection(conn_request)
                        except Exception as e:
                            log('Bank: exception "%s"' % str(e))
                        else:
                            if success:
                                await sirius_sdk.PairwiseList.ensure_exists(pairwise)
                                log('Bank: pairwise established successfully')
                                log(json.dumps(pairwise.metadata, indent=2, sort_keys=True))
                            else:
                                log('Bank: error while establish P2P connection')
                                if feature_0160.problem_report:
                                    log('problem report')
                                    log(json.dumps(feature_0160.problem_report, indent=2, sort_keys=True))
                    else:
                        log(f'Bank: pairwise for {pairwise.their.label} already exists')
                    # Digital service
                    if pairwise is not None:
                        person_name = pairwise.their.label
                        service1 = 'Loan request'
                        service2 = 'Personal offers'
                        ask = sirius_sdk.aries_rfc.Question(
                            valid_responses=[service1, service2],
                            question_text=f'{person_name} welcome to personal cabinet',
                            question_detail='We are glad to make personal offer for you!',
                            locale='en'
                        )
                        ask.set_ttl(60)  # Set timeout for answer
                        success, answer = await sirius_sdk.aries_rfc.ask_and_wait_answer(
                            query=ask,
                            to=pairwise
                        )
                        if success:
                            if answer.response == service1:
                                feature_0037 = sirius_sdk.aries_rfc.Verifier(
                                    prover=pairwise,
                                    ledger=dkms,
                                )
                                verify_ok = await feature_0037.verify(
                                    comment='Prove your salary credentials',
                                    locale='en',
                                    proof_request={
                                        'nonce': await sirius_sdk.AnonCreds.generate_nonce(),
                                        "name": "Proof your salary",
                                        "version": "0.1",
                                        "requested_attributes": {
                                            'attr1_referent': {
                                                "name": "salary",
                                                "restrictions": {
                                                    "issuer_did": DID_EMPLOYER
                                                }
                                            },
                                            'attr2_referent': {
                                                "name": "currency",
                                                "restrictions": {
                                                    "issuer_did": DID_EMPLOYER
                                                }
                                            }
                                        }
                                    },
                                    translation=[
                                        sirius_sdk.aries_rfc.AttribTranslation('salary', 'Your salary'),
                                        sirius_sdk.aries_rfc.AttribTranslation('currency', 'Currency'),
                                    ]
                                )
                                if verify_ok:
                                    txt_msg = sirius_sdk.aries_rfc.Message(
                                        content='Digital service access approved',
                                        locale='en'
                                    )
                                else:
                                    txt_msg = sirius_sdk.aries_rfc.Message(
                                        content='Digital service access declined',
                                        locale='en'
                                    )
                                await sirius_sdk.send_to(txt_msg, pairwise)
                            else:
                                txt_msg = sirius_sdk.aries_rfc.Message(
                                    content='Demo personal offer content',
                                    locale='en'
                                )
                                await sirius_sdk.send_to(txt_msg, pairwise)
                else:
                    log('Bank: Unknown connection-key')


if __name__ == '__main__':
    qr_bank, qr_employer = asyncio.get_event_loop().run_until_complete(generate_invitations_qr_codes())
    print('invitation URLs')
    print(f'Bank: {qr_bank}')
    print(f'Employer: {qr_employer}')
    print('-------------')
    schema_employer, cred_def_employer = asyncio.get_event_loop().run_until_complete(setup_employer_cred_defs())
    asyncio.ensure_future(sirius_bank())
    asyncio.get_event_loop().run_forever()