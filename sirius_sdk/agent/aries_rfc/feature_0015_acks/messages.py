from enum import Enum
from typing import Optional

from ....messaging import Message, Type, check_for_attributes
from ..base import AriesProtocolMessage, AriesProtocolMeta, THREAD_DECORATOR


class Status(Enum):
    # outcome has occurred, and it was positive
    OK = 'OK'

    # no outcome is yet known
    PENDING = 'PENDING'

    # outcome has occurred, and it was negative
    FAIL = 'FAIL'


class Ack(AriesProtocolMessage, metaclass=AriesProtocolMeta):

    PROTOCOL = 'notification'
    NAME = 'ack'

    def __init__(self, thread_id: str=None, status: Optional[Status] = None, *args, **kwargs):
        super(Ack, self).__init__(*args, **kwargs)
        if status is not None:
            self['status'] = status.value
        if thread_id is not None:
            self.get(THREAD_DECORATOR, {}).update({'thid': thread_id})
        else:
            check_for_attributes(self, [THREAD_DECORATOR])
            check_for_attributes(self[THREAD_DECORATOR], ['thid'])

    @property
    def status(self) -> Status:
        status = self.get('status', None)
        if status == Status.OK.value:
            return Status.OK
        elif status == Status.PENDING.value:
            return Status.PENDING
        elif status == Status.FAIL.value:
            return Status.FAIL
        else:
            raise RuntimeError('Unexpected status value')

    @property
    def thread_id(self) -> Optional[str]:
        return self.get(THREAD_DECORATOR, {}).get('thid', None)

    @property
    def please_ack(self) -> Optional[dict]:
        """https://github.com/hyperledger/aries-rfcs/tree/master/features/0317-please-ack"""
        return self.get('~please_ack', None)
