"""
File containing the MultiChain Community.
The MultiChain Community is the first step in an incremental approach in building a new reputation system.
This reputation system builds a tamper proof interaction history contained in a chain data-structure.
Every node has a chain and these chains intertwine by blocks shared by chains.
Full documentation will be available at http://repository.tudelft.nl/.
"""

import logging
import base64
from twisted.internet.task import LoopingCall

from Tribler.Core.Session import Session
from Tribler.Core.CacheDB.sqlitecachedb import forceDBThread

from Tribler.dispersy.authentication import DoubleMemberAuthentication, MemberAuthentication
from Tribler.dispersy.resolution import PublicResolution
from Tribler.dispersy.distribution import DirectDistribution
from Tribler.dispersy.destination import CandidateDestination
from Tribler.dispersy.community import Community
from Tribler.dispersy.message import Message, BatchConfiguration
from Tribler.dispersy.conversion import DefaultConversion

from Tribler.community.tunnel.routing import Circuit, RelayRoute
from Tribler.community.tunnel.tunnel_community import TunnelExitSocket

from Tribler.community.multichain.payload import SignaturePayload, CrawlRequestPayload, CrawlResponsePayload,\
    CrawlResumePayload
from Tribler.community.multichain.database import MultiChainDB, DatabaseBlock
from Tribler.community.multichain.conversion import MultiChainConversion, split_function, HASH_LENGTH

SIGNATURE = u"signature"
CRAWL_REQUEST = u"crawl_request"
CRAWL_RESPONSE = u"crawl_response"
CRAWL_RESUME = u"crawl_resume"

# ID of the first block of the chain.
GENESIS_ID = '0' * HASH_LENGTH

# Divide by this to convert from bytes to MegaBytes.
MEGA_DIVIDER = 1024 * 1024


class MultiChainCommunity(Community):
    """
    Community for reputation based on MultiChain tamper proof interaction history.
    """

    """ Amount of time the MultiChain waits on a signature requests before it times out"""
    signature_request_timeout = 5.0

    def __init__(self, *args, **kwargs):
        super(MultiChainCommunity, self).__init__(*args, **kwargs)
        self.logger = logging.getLogger(self.__class__.__name__)

        from Tribler.Core.simpledefs import NTFY_TUNNEL, NTFY_REMOVE
        Session.get_instance().add_observer(self.on_tunnel_remove, NTFY_TUNNEL, [NTFY_REMOVE])

        self._private_key = self.my_member.private_key
        self._public_key = self.my_member.public_key
        self.persistence = MultiChainDB(self.dispersy, self.dispersy.working_directory)

        # No response is expected yet.
        self.expected_response = None

    def initialize(self, a=None, b=None):
        super(MultiChainCommunity, self).initialize()

    @classmethod
    def get_master_members(cls, dispersy):
        # generated: Wed Dec  3 10:31:16 2014
        # curve: NID_sect571r1
        # len: 571 bits ~ 144 bytes signature
        # pub: 170  3081a7301006072a8648ce3d020106052b810400270381920004059f45b75d63f865e3c7b350bd3ccdc99dbfbf76f
        # dfb524939f070223c3ea9ea5d0536721cf9afbbec5693798e289b964fefc930961dfe1a7f71c445031434aba637bb9
        # 3b947fb81603f649d4a08e5698e677059b9d3a441986c16f8da94d4aa2afbf10fe056cd65741108fe6a880606869c
        # a81fdcb2db302ac15905d6e75f96b39ccdaf068bdbbda81a6356f53f7ce4e
        # pub-sha1 f66a50b35c4a0d45abd0052f574c5ecc233b8e54
        # -----BEGIN PUBLIC KEY-----
        # MIGnMBAGByqGSM49AgEGBSuBBAAnA4GSAAQFn0W3XWP4ZePHs1C9PM3Jnb+/dv37
        # Ukk58HAiM+qepdBTZyHPmvu+xWk3mOKJuWT+/JMJYd/hp/ccRFAxQ0q6Y3u5O5R/
        # uBYD9knUoI5WmOZ3BZudOkQZhsFvjalNSqKvvxD+BWzWV0EQj+aogGBoacqB/cst
        # swKsFZBdbnX5aznM2vBovbvagaY1b1P3zk4=
        # -----END PUBLIC KEY-----
        master_key = "3081a7301006072a8648ce3d020106052b810400270381920004059f45b75d63f865e3c7b350bd3ccdc99dbfbf76f" + \
                     "dfb524939f0702233ea9ea5d0536721cf9afbbec5693798e289b964fefc930961dfe1a7f71c445031434aba637bb9" + \
                     "3b947fb81603f649d4a08e5698e677059b9d3a441986c16f8da94d4aa2afbf10fe056cd65741108fe6a880606869c" + \
                     "a81fdcb2db302ac15905d6e75f96b39ccdaf068bdbbda81a6356f53f7ce4e"
        master_key_hex = master_key.decode("HEX")
        master = dispersy.get_member(public_key=master_key_hex)
        return [master]

    def initiate_meta_messages(self):
        """
        Setup all message that can be received by this community and the super classes.
        :return: list of meta messages.
        """
        return super(MultiChainCommunity, self).initiate_meta_messages() + [
            Message(self, SIGNATURE,
                    DoubleMemberAuthentication(
                        allow_signature_func=self.allow_signature_request, split_payload_func=split_function),
                    PublicResolution(),
                    DirectDistribution(),
                    CandidateDestination(),
                    SignaturePayload(),
                    self._generic_timeline_check,
                    self.received_signature_response),
            Message(self, CRAWL_REQUEST,
                    MemberAuthentication(),
                    PublicResolution(),
                    DirectDistribution(),
                    CandidateDestination(),
                    CrawlRequestPayload(),
                    self._generic_timeline_check,
                    self.received_crawl_request),
            Message(self, CRAWL_RESPONSE,
                    MemberAuthentication(),
                    PublicResolution(),
                    DirectDistribution(),
                    CandidateDestination(),
                    CrawlResponsePayload(),
                    self._generic_timeline_check,
                    self.received_crawl_response,
                    #batch=BatchConfiguration(max_window=1.0)
                    ),
            Message(self, CRAWL_RESUME,
                    MemberAuthentication(),
                    PublicResolution(),
                    DirectDistribution(),
                    CandidateDestination(),
                    CrawlResumePayload(),
                    self._generic_timeline_check,
                    self.received_craw_resumption)]

    def initiate_conversions(self):
        return [DefaultConversion(self), MultiChainConversion(self)]

    def schedule_block(self, candidate, bytes_up, bytes_down):
            """
            Schedule a block for the current outstanding amounts
            :param peer: The peer with whom you have interacted, identified by the (ip, port) tuple
            :param bytes_up: The bytes you have uploaded to the peer in this interaction
            :param bytes_down: The bytes you have downloaded from the peer in this interaction
            """
            self.logger.error("MULTICHAIN: Schedule Block called. Candidate: " + str(candidate) + " UP: " + str(bytes_up) + " DOWN: " + str(bytes_down) )
            self.add_discovered_candidate(candidate)
            if candidate and candidate.get_member():
                self.logger.error("MULTICHAIN: Candidate found" )
                """ Convert to MB """
                total_amount_sent_mb = bytes_up / MEGA_DIVIDER
                total_amount_received_mb = bytes_down / MEGA_DIVIDER

                """ Try to send the request """
                self.publish_signature_request_message(candidate, total_amount_sent_mb, total_amount_received_mb)
            else:
                self.logger.error("MULTICHAIN: Candidate not found" )
                self.logger.warn(
                    "No valid candidate found for: %s:%s to request block from." % (candidate[0], candidate[1]))

    def publish_signature_request_message(self, candidate, up, down):
        #TODO fix description
        """
        Creates and sends out a signed signature_request message if the chain is free for operations.
        If it is the request is sent and True is returned, else False.
        :param candidate: The candidate that the signature request will be sent to.
        :param (int) up: The amount of bytes that have been sent to the candidate that need to signed.
        :param (int) down: The amount of bytes that have been received from the candidate that need to signed.
        return (bool) if request is sent.
        """
        message = self.create_signature_request_message(candidate, up, down)
        self.create_signature_request(candidate, message, self.allow_signature_response,
                                      timeout=self.signature_request_timeout)
        self.persist_signature_request(message)
        return True


    def create_signature_request_message(self, candidate, up, down):
        """
        Create a signature request message using the current time stamp.
        :return: Signature_request message ready for distribution.
        """
        # Instantiate the data
        total_up_requester, total_down_requester = self._get_next_total(up, down)
        # Instantiate the personal information
        sequence_number_requester = self._get_next_sequence_number()
        previous_hash_requester = self._get_latest_hash()

        payload = (up, down, total_up_requester, total_down_requester,
                   sequence_number_requester, previous_hash_requester)
        meta = self.get_meta_message(SIGNATURE)

        message = meta.impl(authentication=([self.my_member, candidate.get_member()],),
                            distribution=(self.claim_global_time(),),
                            payload=payload)
        return message

    def allow_signature_request(self, message):
        """
        We've received a signature request message, we must either:
            a. append to this message our data (Afterwards we sign the message.).
            b. None (if we want to drop this message)
        """
        self.logger.error("MULTICHAIN: Allow Signature?")

        self.logger.info("Received signature request.")
        # TODO: This code always signs a request. Checks and rejects should be inserted here!
        # TODO: Like basic total_up == previous_total_up + block.up or more sophisticated chain checks.
        payload = message.payload

        """ The up and down values are reversed for the responder. """
        total_up_responder, total_down_responder = self._get_next_total(payload.down, payload.up)
        sequence_number_responder = self._get_next_sequence_number()
        previous_hash_responder = self._get_latest_hash()

        payload = (payload.up, payload.down, payload.total_up_requester, payload.total_down_requester,
                   payload.sequence_number_requester, payload.previous_hash_requester,
                   total_up_responder, total_down_responder,
                   sequence_number_responder, previous_hash_responder)

        meta = self.get_meta_message(SIGNATURE)

        message = meta.impl(authentication=(message.authentication.members, message.authentication.signatures),
                            distribution=(message.distribution.global_time,),
                            payload=payload)
        self.persist_signature_response(message)
        self.logger.info("Sending signature response.")
        return message

    def allow_signature_response(self, request, response, modified):
        """
        We've received a signature response message after sending a request, we must return either:
            a. True, if we accept this message
            b. False, if not (because of inconsistencies in the payload)
        """
        if not response:
            self.logger.info("Timeout received for signature request.")
            # Unpack the message from the cache object and store a half-signed record.
        #    self.persist_signature_response(request.request.payload.message)
            return False
        else:
            # TODO: Check expecting response
            self.logger.info("Signature response received. Modified: %s" % modified)

            if request.payload.sequence_number_requester == response.payload.sequence_number_requester and \
               request.payload.previous_hash_requester == response.payload.previous_hash_requester and modified:
                block = DatabaseBlock.from_signature_response_message(response)
                self.persistence.update_block(block)
                return True
            else:
                return False

    def received_signature_response(self, messages):
        """
        We've received a valid signature response and must process this message.
        """
        self.logger.info("Valid %s signature response(s) received." % len(messages))
        for message in messages:
            self.persist_signature_response(message)
            # Release exclusion flag because the operation is done.
            self.logger.debug("Chain exclusion: released received signature response.")

    def persist_signature_response(self, message):
        """
        Persist the signature response message.
        A hash will be created from the message and this will be used as an unique identifier.
        :param message:
        """
        block = DatabaseBlock.from_signature_response_message(message)
        self.logger.info("Persisting sr: %s" % base64.encodestring(block.hash_requester).strip())
        self.persistence.add_block(block)

    def persist_signature_request(self, message):
        """
        Persist the signature request message as a block.
        The block will be updated when a response is received.
        :param message:
        """
        block = DatabaseBlock.from_signature_request_message(message)
        self.logger.info("Persisting sr: %s" % base64.encodestring(block.hash_requester).strip())
        self.persistence.add_block(block)

    def send_crawl_request(self, candidate, sequence_number = None):
        if sequence_number is None:
            sequence_number = self.persistence.get_latest_sequence_number(candidate.get_member().mid);
        self.logger.info("Crawler: Requesting crawl from node %s, from sequence number %d" % (base64.encodestring(candidate.get_member().mid).strip(), sequence_number))
        meta = self.get_meta_message(CRAWL_REQUEST)
        message = meta.impl(authentication=(self.my_member,),
                            distribution=(self.claim_global_time(),),
                            destination=(candidate,),
                            payload=(sequence_number,))
        self.dispersy.store_update_forward([message], False, False, True)

    def received_crawl_request(self, messages):
        for message in messages:
            self.logger.info("Crawler: Received crawl request from node %s, from sequence number %d" %
                             (base64.encodestring(message.candidate.get_member().mid).strip(), message.payload.requested_sequence_number))
            self.crawl_requested(message.candidate, message.payload.requested_sequence_number)

    def crawl_requested(self, candidate, sequence_number):
        blocks = self.persistence.get_blocks_since(self.private_key, sequence_number)
        if len(blocks) > 0:
            self.logger.info("Crawler: Sending %d blocks" % len(blocks))
            messages = [self.get_meta_message(CRAWL_RESPONSE)
                    .impl(authentication=(self.my_member,),
                          distribution=(self.claim_global_time(),),
                          destination=(candidate,),
                          payload=block.to_payload()) for block in blocks]
            self.dispersy.store_update_forward(messages, False, False, True)
            if len(blocks) > 1:
                # we sent more than 1 block. Send a resumption token so the other side knows it should continue crawling
                #last_block = blocks[-1]
                #resumption_number = last_block.sequence_number_requster if last_block.mid_requester == self._mid else last_block.sequence_number_responder
                message = self.get_meta_message(CRAWL_RESUME).impl(authentication=(self.my_member,),
                          distribution=(self.claim_global_time(),),
                          destination=(candidate,),
                #          payload=(resumption_number))
                          payload=())
                self.dispersy.store_update_forward([message], False, False, True)
        else:
            # This is slightly worrying since the last block should always be returned.
            # Or rather, the other side is requesting blocks starting from a point in the future.
            self.logger.info("Crawler: No blocks")

    def received_crawl_response(self, messages):
        self.logger.info("Crawler: Valid %d block response(s) received." % len(messages))
        for message in messages:
            requester = self.dispersy.get_member(public_key=message.payload.public_key_requester)
            responder = self.dispersy.get_member(public_key=message.payload.public_key_responder)
            block = DatabaseBlock.from_block_response_message(message, requester, responder)
            # Create the hash of the message
            if not self.persistence.contains(block.id):
                self.logger.info("Crawler: Persisting id: %s" % base64.encodestring(block.id).strip())
                self.persistence.add_block(block)
            else:
                self.logger.info("Crawler: Received already known block")

    def received_craw_resumption(self, messages):
        self.logger.info("Crawler: Valid %s crawl resumptions received." % len(messages))
        for message in messages:
            self.send_crawl_request(message.candidate)

    def get_key(self):
        return self._private_key

    def _get_next_total(self, up, down):
        """
        Returns the next total numbers of up and down incremented with the current interaction up and down metric.
        :param up: Up metric for the interaction.
        :param down: Down metric for the interaction.
        :return: (total_up (int), total_down (int)
        """
        total_up, total_down = self.persistence.get_total(self._public_key)
        if total_up == total_down == -1:
            return up, down
        else:
            return total_up + up, total_down + down

    def _get_next_sequence_number(self):
        return self.persistence.get_latest_sequence_number(self._public_key) + 1

    def _get_latest_hash(self):
        previous_hash = self.persistence.get_latest_hash(self._public_key)
        return previous_hash if previous_hash else GENESIS_ID

    def unload_community(self):
        self.logger.debug("Unloading the MultiChain Community.")
        super(MultiChainCommunity, self).unload_community()
        # Close the persistence layer
        self.persistence.close()

    @forceDBThread
    def on_tunnel_remove(self, subject, changeType, tunnel, stats, candidate):
        """
        Handler for the remove event of a tunnel. This function will attempt to create a block for the amounts that
        were transferred using the tunnel.
        :param subject:
        :param changeType:
        :param tunnel: The tunnel that was removed (closed)
        :param stats: The statistics regarding this tunnel
        :return:
        """

        self.logger.error("MULTICHAIN: on_tunnel_remove_called" + str(type(tunnel)) + str(stats))

        bytes_up = None
        bytes_down = None
        if isinstance(tunnel, Circuit):
            bytes_up = stats['bytes_up']
            bytes_down = stats['bytes_down']
            peer = (tunnel.first_hop[0], tunnel.first_hop[1])
        elif isinstance(tunnel, RelayRoute):
            bytes_up = stats['bytes_relay_up']
            bytes_down = stats['bytes_relay_down']
            peer = (tunnel.sock_addr[0], tunnel.sock_addr[1])
        elif isinstance(tunnel, TunnelExitSocket):
            bytes_up = stats['bytes_exit']
            bytes_down = stats['bytes_enter']
            peer = (tunnel.sock_addr[0], tunnel.sock_addr[1])
        else:
            self.logger.error("Got a tunnel remove event for an object that is not a Circuit, RelayRoute or TunnelExitSocket")
            raise TypeError("Got a tunnel remove event for an object that is not a Circuit, RelayRoute or TunnelExitSocket")

        self.logger.error("MULTICHAIN: parsed tunnel info")


        if isinstance(bytes_up, int) and isinstance(bytes_down, int):
           # if bytes_up > bytes_down:
                self.schedule_block(candidate, bytes_up, bytes_down)
            #else:
                #TODO Note that you still expect a signature request for these bytes:
                #pending[peer] = (up, down)

class MultiChainCommunityCrawler(MultiChainCommunity):
    """
    Extended MultiChainCommunity that also crawls other MultiChainCommunities.
    It requests the chains of other MultiChains.
    """

    """ Time the crawler waits between crawling a new candidate."""
    CrawlerDelay = 5.0

    def __init__(self, *args, **kwargs):
        super(MultiChainCommunityCrawler, self).__init__(*args, **kwargs)

    def on_introduction_response(self, messages):
        super(MultiChainCommunityCrawler, self).on_introduction_response(messages)
        for message in messages:
            self.send_crawl_request(message.candidate)

    def start_walking(self):
        self.register_task("take step", LoopingCall(self.take_step)).start(self.CrawlerDelay, now=True)