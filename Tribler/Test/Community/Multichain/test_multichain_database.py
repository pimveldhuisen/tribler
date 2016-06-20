import datetime
import os
from math import pow

from Tribler.Test.Community.Multichain.test_multichain_utilities import TestBlock, MultiChainTestCase
from Tribler.community.multichain.database import MultiChainDB
from Tribler.community.multichain.database import DATABASE_DIRECTORY


class TestDatabase(MultiChainTestCase):
    """
    Tests the Database for MultiChain community.
    """

    def __init__(self, *args, **kwargs):
        super(TestDatabase, self).__init__(*args, **kwargs)

    def setUp(self, **kwargs):
        super(TestDatabase, self).setUp()
        path = os.path.join(self.getStateDir(), DATABASE_DIRECTORY)
        if not os.path.exists(path):
            os.makedirs(path)
        self.db = MultiChainDB(self.getStateDir())
        self.block1 = TestBlock()
        self.block2 = TestBlock()

    def test_add_block(self):
        # Act
        self.db.add_block(self.block1)
        # Assert
        result = self.db.get_latest(self.block1.public_key)
        self.assertEqual_block(self.block1, result)

    def test_add_two_blocks(self):
        # Act
        self.db.add_block(self.block1)
        self.db.add_block(self.block2)
        # Assert
        result = self.db.get_latest(self.block2.public_key)
        self.assertEqual_block(self.block2, result)

    def test_get_block_non_existing(self):
        # Act
        result = self.db.get_latest(self.block1.public_key)
        # Assert
        self.assertEqual(None, result)

    def test_contains_block_id_positive(self):
        # Act
        self.db.add_block(self.block1)
        # Assert
        assert self.db.contains(self.block1)

    def test_contains_block_id_negative(self):
        # Act & Assert
        assert not self.db.contains(self.block1)

    def test_get_linked_forward(self):
        # Arrange
        self.block2 = TestBlock.create(self.db, self.block2.public_key, link=self.block1)
        self.db.add_block(self.block1)
        self.db.add_block(self.block2)
        # Act
        result = self.db.get_linked(self.block1)
        # Assert
        self.assertEqual_block(self.block2, result)

    def test_get_linked_backwards(self):
        # Arrange
        self.block2 = TestBlock.create(self.db, self.block2.public_key, link=self.block1)
        self.db.add_block(self.block1)
        self.db.add_block(self.block2)
        # Act
        result = self.db.get_linked(self.block2)
        # Assert
        self.assertEqual_block(self.block1, result)

    def test_get_blocks_since(self):
        # Arrange
        self.block2.public_key = self.block1.public_key
        self.block2.sequence_number = self.block1.sequence_number + 1
        block3 = TestBlock()
        block3.public_key = self.block2.public_key
        block3.sequence_number = self.block2.sequence_number + 10
        self.db.add_block(self.block1)
        self.db.add_block(self.block2)
        self.db.add_block(block3)
        # Act
        result = self.db.get_blocks_since(self.block2.public_key, self.block2.sequence_number)
        # Assert
        self.assertEqual(len(result), 2)
        self.assertEqual_block(self.block2, result[0])
        self.assertEqual_block(block3, result[1])

    def test_get_blocks_until(self):
        # Arrange
        self.block2.public_key = self.block1.public_key
        self.block2.sequence_number = self.block1.sequence_number + 1
        block3 = TestBlock()
        block3.public_key = self.block2.public_key
        block3.sequence_number = self.block2.sequence_number + 10
        self.db.add_block(self.block1)
        self.db.add_block(self.block2)
        self.db.add_block(block3)
        # Act
        result = self.db.get_blocks_until(self.block2.public_key, self.block2.sequence_number)
        # Assert
        self.assertEqual(len(result), 2)
        self.assertEqual_block(self.block1, result[0])
        self.assertEqual_block(self.block2, result[1])

    def test_save_large_upload_download_block(self):
        """
        Test if the block can save very large numbers.
        """
        # Arrange
        self.block1.total_up = long(pow(2, 62))
        self.block1.total_down = long(pow(2, 62))
        # Act
        self.db.add_block(self.block1)
        # Assert
        result = self.db.get_latest(self.block1.public_key)
        self.assertEqual_block(self.block1, result)

    def test_get_insert_time(self):
        # Arrange
        # Upon adding the block to the database, the timestamp will get added.
        self.db.add_block(self.block1)

        # Act
        # Retrieving the block from the database will result in a block with a timestamp
        result = self.db.get_latest(self.block1.public_key)

        insert_time = datetime.datetime.strptime(result.insert_time,
                                                 "%Y-%m-%d %H:%M:%S")

        # We store UTC timestamp
        time_difference = datetime.datetime.utcnow() - insert_time

        # Assert
        self.assertEquals(time_difference.days, 0)
        self.assertLess(time_difference.seconds, 10,
                        "Difference in stored and retrieved time is too large.")

    def set_db_version(self, version):
        self.db.executescript(u"UPDATE option SET value = '%d' WHERE key = 'database_version';" % version)
        self.db.close(commit=True)
        self.db = MultiChainDB(self.getStateDir())

    def test_database_upgrade(self):
        self.set_db_version(1)
        version, = next(self.db.execute(u"SELECT value FROM option WHERE key = 'database_version' LIMIT 1"))
        self.assertEqual(version, u"2")

    def test_database_create(self):
        self.set_db_version(0)
        version, = next(self.db.execute(u"SELECT value FROM option WHERE key = 'database_version' LIMIT 1"))
        self.assertEqual(version, u"2")

    def test_database_no_downgrade(self):
        self.set_db_version(200000)
        version, = next(self.db.execute(u"SELECT value FROM option WHERE key = 'database_version' LIMIT 1"))
        self.assertEqual(version, u"200000")
