"""
This file contains the tests for the community.py for MultiChain community.
"""
from time import sleep

from unittest.case import skip

from nose.tools import raises
from twisted.internet.defer import inlineCallbacks

from Tribler.Core.Session import Session

from Tribler.Test.Community.Multichain.test_multichain_utilities import MultiChainTestCase

from Tribler.community.multichain.community import (MultiChainCommunity, MultiChainCommunityCrawler, HALF_BLOCK, CRAWL,
                                                    PendingBytes)
from Tribler.community.multichain.block import MultiChainBlock, GENESIS_SEQ

from Tribler.community.tunnel.routing import Circuit, RelayRoute
from Tribler.community.tunnel.tunnel_community import TunnelExitSocket
from Tribler.Test.test_as_server import AbstractServer
from Tribler.dispersy.tests.dispersytestclass import DispersyTestFunc
from Tribler.dispersy.util import blocking_call_on_reactor_thread
from Tribler.dispersy.tests.debugcommunity.node import DebugNode
from Tribler.dispersy.candidate import Candidate
from Tribler.dispersy.requestcache import IntroductionRequestCache


class TestMultiChainCommunity(MultiChainTestCase, DispersyTestFunc):
    """
    Class that tests the MultiChainCommunity on an integration level.
    """

    class MockSession():
        def add_observer(self, func, subject, changeTypes=[], objectID=None, cache=0):
            pass

    @blocking_call_on_reactor_thread
    @inlineCallbacks
    def setUp(self):
        Session.__single = self.MockSession()
        AbstractServer.setUp(self)
        yield DispersyTestFunc.setUp(self)

    def tearDown(self):
        Session.del_instance()
        DispersyTestFunc.tearDown(self)
        AbstractServer.tearDown(self)

    def test_on_tunnel_remove(self):
        """
        Test the on_tunnel_remove handler function for a circuit
        """
        # Arrange
        node, other = self.create_nodes(2)
        tunnel_node = Circuit(long(0), 0)
        tunnel_other = Circuit(long(0), 0)
        tunnel_node.bytes_up = tunnel_other.bytes_down = 12 * 1024 * 1024
        tunnel_node.bytes_down = tunnel_other.bytes_up = 14 * 1024 * 1024

        # Act
        node.call(node.community.on_tunnel_remove, None, None, tunnel_node, self._create_target(node, other))
        other.call(other.community.on_tunnel_remove, None, None, tunnel_other, self._create_target(other, node))
        sleep(5.1)

        # Assert
        _, signature_request = node.receive_message(names=[HALF_BLOCK]).next()
        node.give_message(signature_request, other)
        _, signature_request = other.receive_message(names=[HALF_BLOCK]).next()
        other.give_message(signature_request, node)

        self.assertBlocksInDatabase(node, 2)
        self.assertBlocksInDatabase(other, 2)
        self.assertBlocksAreEqual(node, other)

    def test_on_tunnel_remove_append_pending(self):
        """
        Test the on_tunnel_remove handler function for a circuit
        """
        # Arrange
        node, other = self.create_nodes(2)
        tunnel_node = Circuit(long(0), 0)
        tunnel_node.bytes_up = 12 * 1024 * 1024
        tunnel_node.bytes_down = 14 * 1024 * 1024

        # Act
        node.call(node.community.on_tunnel_remove, None, None, tunnel_node, self._create_target(node, other))
        node.call(node.community.on_tunnel_remove, None, None, tunnel_node, self._create_target(node, other))
        sleep(5.1)

        self.assertEqual(node.community.pending_bytes[other.community.my_member.public_key].up, 2*tunnel_node.bytes_up)
        self.assertEqual(node.community.pending_bytes[other.community.my_member.public_key].down,
                         2*tunnel_node.bytes_down)

    def test_sign_block(self):
        """
        Test the community to send a signature request message.
        """
        node, other = self.create_nodes(2)
        target_other = self._create_target(node, other)
        # Act
        node.call(node.community.sign_block, target_other, 5, 5)
        # Assert
        _, message = other.receive_message(names=[HALF_BLOCK]).next()
        self.assertTrue(message)

    def test_sign_invalid_block(self):
        """
        Test the community to publish a signature request message.
        """
        node, other = self.create_nodes(2)
        target_other = self._create_target(node, other)
        # Act
        node.call(node.community.sign_block, target_other, 0, 0)
        # Assert

        with self.assertRaises(StopIteration):
            # No signature requests
            other.receive_message(names=[HALF_BLOCK]).next()


    def test_schedule_block_invalid_candidate(self):
        """
        Test the schedule_block function with an invalid candidate
        """
        # Arrange
        [node] = self.create_nodes(1)
        candidate = Candidate(("127.0.0.1", 10), False)
        # Act
        node.call(node.community.sign_block, candidate, 5, 5)

    def test_receive_signature_request_and_response(self):
        """
        Test the community to receive a signature request and a signature response message.
        """
        # Arrange
        node, other = self.create_nodes(2)

        # Act
        TestMultiChainCommunity.create_block(node, other, self._create_target(node, other), 10, 5)

        # Assert
        self.assertBlocksInDatabase(other, 2)
        self.assertBlocksInDatabase(node, 2)
        self.assertBlocksAreEqual(node, other)

        block = node.call(node.community.persistence.get_latest, node.community.my_member.public_key)
        linked = node.call(node.community.persistence.get_linked, block)
        self.assertNotEquals(linked, None)

        block = other.call(other.community.persistence.get_latest, other.community.my_member.public_key)
        linked = other.call(other.community.persistence.get_linked, block)
        self.assertNotEquals(linked, None)

    def test_receive_request_invalid(self):
        """
        Test the community to receive a request message.
        """
        # Arrange
        node, other = self.create_nodes(2)
        target_other = self._create_target(node, other)
        TestMultiChainCommunity.set_expectation(other, node, 10, 5)
        node.call(node.community.sign_block, target_other, 10, 5)
        _, block_req = other.receive_message(names=[HALF_BLOCK]).next()
        # Act
        # construct faked block
        block = block_req.payload.block
        block.up += 10
        block.total_up = block.up
        block_req = node.community.get_meta_message(HALF_BLOCK).impl(
            authentication=(node.community.my_member,),
            distribution=(node.community.claim_global_time(),),
            destination=(target_other,),
            payload=(block,))
        other.give_message(block_req, node)

        # Assert
        self.assertBlocksInDatabase(other, 0)
        self.assertBlocksInDatabase(node, 1)

        with self.assertRaises(StopIteration):
            # No signature responses, or crawl requests should have been sent
            node.receive_message(names=[HALF_BLOCK, CRAWL]).next()

    def test_receive_request_too_much(self):
        """
        Test the community to receive a request that claims more than we are prepared to sign
        """
        # Arrange
        node, other = self.create_nodes(2)
        target_other = self._create_target(node, other)
        TestMultiChainCommunity.set_expectation(other, node, 3, 3)
        node.call(node.community.sign_block, target_other, 10, 5)
        # Act
        other.give_message(other.receive_message(names=[HALF_BLOCK]).next()[1], node)

        # Assert
        self.assertBlocksInDatabase(other, 1)
        self.assertBlocksInDatabase(node, 1)

        with self.assertRaises(StopIteration):
            # No signature responses, or crawl requests should have been sent
            node.receive_message(names=[HALF_BLOCK, CRAWL]).next()

    def test_block_values(self):
        """
        If a block is created between two nodes both
        should have the correct total_up and total_down of the signature request.
        """
        # Arrange
        node, other = self.create_nodes(2)

        # Act
        TestMultiChainCommunity.create_block(node, other, self._create_target(node, other), 10, 5)

        # Assert
        block = node.call(MultiChainBlock.create, node.community.persistence, node.community.my_member.public_key)
        self.assertEqual(10, block.total_up)
        self.assertEqual(5, block.total_down)
        block = other.call(MultiChainBlock.create, other.community.persistence, other.community.my_member.public_key)
        self.assertEqual(5, block.total_up)
        self.assertEqual(10, block.total_down)

    def test_block_values_after_request(self):
        """
        After a request is sent, a node should update its totals.
        """
        # Arrange
        node, other = self.create_nodes(2)
        node.call(node.community.sign_block, self._create_target(node, other), 10, 5)

        # Assert
        block = node.call(MultiChainBlock.create, node.community.persistence, node.community.my_member.public_key)
        self.assertEqual(10, block.total_up)
        self.assertEqual(5, block.total_down)

    def test_crawl_on_partial(self):
        """
        Test that a crawl is requested if the signer cannot validate the previous hash of a request
        """
        # Arrange
        node, other, another = self.create_nodes(3)

        # Act
        TestMultiChainCommunity.create_block(node, other, self._create_target(node, other), 10, 5)

        TestMultiChainCommunity.set_expectation(another, node, 30, 20)
        node.call(node.community.sign_block, self._create_target(node, another), 30, 20)
        another.give_message(another.receive_message(names=[HALF_BLOCK]).next()[1], node)

        # Assert
        message = node.receive_message(names=[CRAWL]).next()[1]
        self.assertTrue(message)

    def test_crawl_on_partial_complete(self):
        """
        Test that a crawl is requested and serviced if the signer cannot validate the previous hash of a request
        """
        # Arrange
        node, other, another = self.create_nodes(3)

        # Act
        TestMultiChainCommunity.create_block(node, other, self._create_target(node, other), 10, 5)
        TestMultiChainCommunity.create_block(node, another, self._create_target(node, another), 20, 30)

        # Assert
        self.assertBlocksInDatabase(node, 4)
        self.assertBlocksInDatabase(other, 2)
        self.assertBlocksInDatabase(another, 4)
        self.assertBlocksAreEqual(node, another)

    def test_crawl_block_latest(self):
        """
        Test the crawler to request the latest block.
        """
        # Arrange
        node, other, crawler = self.create_nodes(3)

        # Act
        TestMultiChainCommunity.create_block(node, other, self._create_target(node, other), 10, 5)
        TestMultiChainCommunity.crawl_node(crawler, node, self._create_target(crawler, node))

        # Assert
        self.assertBlocksInDatabase(node, 2)
        self.assertBlocksInDatabase(crawler, 2)
        self.assertBlocksAreEqual(node, crawler)

    def test_crawl_block_specified_sequence_number(self):
        """
        Test the crawler to fetch a block with a specified sequence number.
        """
        # Arrange
        node, other, crawler = self.create_nodes(3)

        # Act
        TestMultiChainCommunity.create_block(node, other, self._create_target(node, other), 10, 5)
        TestMultiChainCommunity.crawl_node(crawler, node, self._create_target(crawler, node), GENESIS_SEQ)

        # Assert
        self.assertBlocksInDatabase(node, 2)
        self.assertBlocksInDatabase(crawler, 2)
        self.assertBlocksAreEqual(node, crawler)

    def test_crawl_no_block(self):
        """
        Test crawl without a block.
        """
        # Arrange
        node, crawler = self.create_nodes(2)

        # Act
        TestMultiChainCommunity.crawl_node(crawler, node, self._create_target(crawler, node))

        self.assertBlocksInDatabase(node, 0)
        self.assertBlocksInDatabase(crawler, 0)

    def test_crawl_block_known(self):
        """
        Test the crawler to request a known block.
        """
        # Arrange
        node, other, crawler = self.create_nodes(3)

        TestMultiChainCommunity.create_block(node, other, self._create_target(node, other), 10, 5)
        TestMultiChainCommunity.crawl_node(crawler, other, self._create_target(crawler, other))

        # Act
        # Request the same blocks form different node
        TestMultiChainCommunity.crawl_node(crawler, node, self._create_target(crawler, node))

        # Assert
        self.assertBlocksInDatabase(node, 2)
        self.assertBlocksInDatabase(crawler, 2)
        self.assertBlocksAreEqual(node, crawler)

    def test_crawl_batch(self):
        """
        Test the crawler for fetching multiple blocks in one crawl.
        """
        # Arrange
        node, other, crawler = self.create_nodes(3)
        target_other = self._create_target(node, other)

        TestMultiChainCommunity.create_block(node, other, target_other, 10, 5)
        TestMultiChainCommunity.create_block(node, other, target_other, 20, 30)

        # Act
        # Request the same block
        TestMultiChainCommunity.crawl_node(crawler, node, self._create_target(crawler, node))

        # Assert
        self.assertBlocksInDatabase(node, 4)
        self.assertBlocksInDatabase(other, 4)
        self.assertBlocksInDatabase(crawler, 4)
        self.assertBlocksAreEqual(node, other)
        self.assertBlocksAreEqual(node, crawler)
        self.assertBlocksAreEqual(other, crawler)

    def test_crawler_on_introduction_received(self):
        """
        Test the crawler takes a step when an introduction is made by the walker
        """
        # Arrange
        MultiChainCommunityCrawler.CrawlerDelay = 10000000
        crawler = super(TestMultiChainCommunity, self).create_nodes(1, community_class=MultiChainCommunityCrawler,
                                                                    memory_database=False)[0]
        node, = self.create_nodes(1)
        node._community.cancel_pending_task("take fast steps")
        node._community.cancel_pending_task("take step")
        node._community.cancel_pending_task("start_walking")
        target_node_from_crawler = self._create_target(node, crawler)

        # when we call on_introduction request it is going to forward the argument to it's super implementation.
        # Dispersy will error if it does not expect this, and the target code will not be tested. So we pick at
        # dispersy's brains to make it accept the intro response.
        intro_request_info = crawler.call(IntroductionRequestCache , crawler.community, None)
        intro_response = node.create_introduction_response(target_node_from_crawler, node.lan_address, node.wan_address,
                                                           node.lan_address, node.wan_address,
                                                           u"unknown", False, intro_request_info.number)
        intro_response._candidate = target_node_from_crawler
        crawler.community.request_cache._identifiers[
            crawler.community.request_cache._create_identifier(intro_request_info.number, u"introduction-request")
        ] = intro_request_info

        # and we don't actually want to send the crawl request since the counter party is fake, just count if it is run
        counter = [0]
        def replacement(cand):
            counter[0] += 1
        crawler._community.send_crawl_request = replacement

        # Act
        crawler.call(crawler.community.on_introduction_response, [intro_response])

        # Assert
        self.assertEqual(counter[0], 1)

    def test_get_statistics_no_blocks(self):
        """
        Test the get_statistics method where last block is none
        """
        node, = self.create_nodes(1)
        statistics = node.community.get_statistics()
        assert isinstance(statistics, dict), type(statistics)
        assert len(statistics) > 0

    def test_get_statistics_with_previous_block(self):
        """
        Test the get_statistics method where a last block exists
        """
        # Arrange
        node, other = self.create_nodes(2)
        TestMultiChainCommunity.create_block(node, other, self._create_target(node, other), 10, 5)

        # Get statistics
        statistics = node.community.get_statistics()
        assert isinstance(statistics, dict), type(statistics)
        assert len(statistics) > 0

    @blocking_call_on_reactor_thread
    def assertBlocksInDatabase(self, node, amount):
        count = node.community.persistence.execute(u"SELECT COUNT(*) FROM multi_chain").fetchone()[0]
        assert count == amount, "Wrong number of blocks in database, was {0} but expected {1}".format(count, amount)

    @blocking_call_on_reactor_thread
    def assertBlocksAreEqual(self, node, other):
        map(self.assertEqual_block,
            node.community.persistence.crawl(node.community.my_member.public_key, 0),
            other.community.persistence.crawl(node.community.my_member.public_key, 0))
        map(self.assertEqual_block,
            node.community.persistence.crawl(other.community.my_member.public_key, 0),
            other.community.persistence.crawl(other.community.my_member.public_key, 0))

    @staticmethod
    def set_expectation(node, req, up, down):
        if node.community.pending_bytes.get(req.community.my_member.public_key):
            node.community.pending_bytes[req.community.my_member.public_key].add(down, up)
        else:
            node.community.pending_bytes[req.community.my_member.public_key] = PendingBytes(down, up)

    @staticmethod
    def create_block(req, resp, target_resp, up, down):
        TestMultiChainCommunity.set_expectation(resp, req, up, down)
        req.call(req.community.sign_block, target_resp, up, down)
        resp.give_message(resp.receive_message(names=[HALF_BLOCK]).next()[1], req)
        half_or_crawl = req.receive_message(names=[HALF_BLOCK, CRAWL]).next()[1]
        req.give_message(half_or_crawl, resp)
        while half_or_crawl.name == CRAWL:
            sleep(0.5)
            TestMultiChainCommunity.transport_halfblocks(req, resp)
            sleep(5.5)
            half_or_crawl = req.receive_message(names=[HALF_BLOCK, CRAWL]).next()[1]
            req.give_message(half_or_crawl, resp)

    @staticmethod
    def crawl_node(crawler, crawlee, target_to_crawlee, sequence_number=None):
        crawler.call(crawler.community.send_crawl_request, target_to_crawlee, sequence_number)
        crawlee.give_message(crawlee.receive_message(names=[CRAWL]).next()[1], crawler)
        TestMultiChainCommunity.transport_halfblocks(crawlee, crawler)

    @staticmethod
    def transport_halfblocks(source, sink):
        count = -1
        while count != 0:
            count = 0
            try:
                gen = sink.receive_message(names=[HALF_BLOCK])
                message = gen.next()[1]
                while message:
                    count += 1
                    sink.give_message(message, source)
                    message = gen.next()[1]
            except StopIteration:
                pass

    def create_nodes(self, *args, **kwargs):
        nodes = super(TestMultiChainCommunity, self).create_nodes(*args, community_class=MultiChainCommunity,
                                                                 memory_database=False, **kwargs)
        for x in nodes:
            for y in nodes:
                if x != y:
                    x.send_identity(y)

        return nodes

    def _create_node(self, dispersy, community_class, c_master_member):
        return DebugNode(self, dispersy, community_class, c_master_member, curve=u"curve25519")

    @blocking_call_on_reactor_thread
    def _create_target(self, source, destination):
        target = destination.my_candidate
        target.associate(source._dispersy.get_member(public_key=destination.my_pub_member.public_key))
        return target
