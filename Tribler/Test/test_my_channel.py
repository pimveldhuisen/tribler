# Written by Niels Zeilemaker
# see LICENSE.txt for license information

from binascii import hexlify
import os
import shutil
from Tribler.Core.Utilities.network_utils import get_random_port

from Tribler.Test.common import UBUNTU_1504_INFOHASH
from Tribler.Test.test_libtorrent_download import TORRENT_FILE, TORRENT_VIDEO_FILE
from Tribler.Test.test_as_server import TestGuiAsServer, TESTS_DATA_DIR

from Tribler.Core.TorrentDef import TorrentDef

DEBUG = True


class TestMyChannel(TestGuiAsServer):

    def setUp(self):
        super(TestMyChannel, self).setUp()

        # Prepare test_rss.xml file, replace the port with a random one
        self.file_server_port = get_random_port()
        with open(os.path.join(TESTS_DATA_DIR, 'test_rss.xml'), 'r') as source_xml,\
                open(os.path.join(self.session_base_dir, 'test_rss.xml'), 'w') as destination_xml:
                for line in source_xml:
                    destination_xml.write(line.replace('RANDOMPORT', str(self.file_server_port)))

        # Setup file server to serve torrent file and thumbnails
        files_path = os.path.join(self.session_base_dir, 'http_torrent_files')
        os.mkdir(files_path)
        shutil.copyfile(TORRENT_FILE, os.path.join(files_path, 'ubuntu.torrent'))
        shutil.copyfile(TORRENT_VIDEO_FILE, os.path.join(files_path, 'video.torrent'))
        shutil.copyfile(os.path.join(TESTS_DATA_DIR, 'ubuntu-logo14.png'),
                        os.path.join(files_path, 'ubuntu-logo14.png'))
        self.setUpFileServer(self.file_server_port, files_path)

    def test_rss_import(self):
        def do_files_check():
            self.screenshot('Torrents imported')
            self.quit()

        def added_rss():
            self.screenshot('Rssfeed added')

            # switch to files tab
            mt_index = self.managechannel.GetPage(self.managechannel.notebook, "Manage torrents")
            self.managechannel.notebook.SetSelection(mt_index)

            managefiles = self.managechannel.fileslist
            self.CallConditional(
                60, lambda: len(managefiles.GetItems()) > 0, do_files_check, 'Channel did not have torrents')

        def do_rss():
            self.managechannel.rss_url.SetValue(os.path.join(self.session_base_dir, 'test_rss.xml'))
            self.managechannel.OnAddRss()

            # switch to manage tab
            m_index = self.managechannel.GetPage(self.managechannel.notebook, "Manage")
            self.managechannel.notebook.SetSelection(m_index)

            self.callLater(1, added_rss)

        def do_create():
            self.managechannel = self.frame.managechannel

            self.managechannel.name.SetValue('UNITTEST')
            self.managechannel.description.SetValue('Channel created for UNITTESTING purposes')

            self.managechannel.Save()
            self.CallConditional(60, lambda: self.frame.managechannel.rss_url,
                                 do_rss, 'Channel instance did not arrive at managechannel')

        def do_page():
            self.guiUtility.ShowPage('mychannel')
            self.callLater(1, do_create)

        self.startTest(do_page)

    def test_add_torrents_playlists(self):

        def do_overview():
            self.guiUtility.showChannel(self.managechannel.channel)
            self.screenshot('Resulting channel')
            self.quit()

        def do_create_playlist(torrentfilename):
            self.screenshot('Files have been added created')

            infohash = TorrentDef.load(torrentfilename).get_infohash()

            manageplaylist = self.managechannel.playlistlist
            manager = manageplaylist.GetManager()
            manager.createPlaylist('Unittest', 'Playlist created for Unittest', [infohash, ])

            # switch to playlist tab
            mp_index = self.managechannel.GetPage(self.managechannel.notebook, "Manage playlists")
            self.managechannel.notebook.SetSelection(mp_index)

            self.CallConditional(
                60, lambda: len(manageplaylist.GetItems()) == 1, do_overview, 'Channel did not have a playlist')

        def do_switch_tab(torrentfilename):
            # switch to files tab
            mt_index = self.managechannel.GetPage(self.managechannel.notebook, "Manage torrents")
            self.managechannel.notebook.SetSelection(mt_index)

            self.CallConditional(120, lambda: len(self.managechannel.fileslist.GetItems()) == 3,
                                 lambda: do_create_playlist(torrentfilename), 'Channel did not have 3 torrents')

        def do_add_torrent(torrentfilename):
            self.screenshot('Channel is created')

            managefiles = self.managechannel.fileslist
            manager = managefiles.GetManager()
            manager.startDownload(torrentfilename, fixtorrent=True)
            manager.startDownloadFromUrl(r'http://localhost:%s/video.torrent' % self.file_server_port, fixtorrent=True)
            manager.startDownloadFromMagnet(
                r'magnet:?xt=urn:btih:%s&dn=ubuntu-14.04.2-desktop-amd64.iso' % hexlify(UBUNTU_1504_INFOHASH), fixtorrent=True)

            self.CallConditional(
                10, lambda: self.managechannel.notebook.GetPageCount() > 1, lambda: do_switch_tab(torrentfilename))

        def do_create_local_torrent():
            torrentfilename = self.createTorrent()
            do_add_torrent(torrentfilename)

        def do_create():
            self.screenshot('After selecting mychannel page')

            self.managechannel = self.frame.managechannel

            self.managechannel.name.SetValue('UNITTEST')
            self.managechannel.description.SetValue('Channel created for UNITTESTING purposes')

            self.managechannel.Save()
            self.screenshot('After clicking save')

            self.CallConditional(60, lambda: self.frame.managechannel.channel,
                                 do_create_local_torrent, 'Channel instance did not arrive at managechannel')

        def do_page():
            self.guiUtility.ShowPage('mychannel')
            self.callLater(1, do_create)

        self.startTest(do_page)

    def test_metadata(self):
        """
        Uses RSS feed to test metadata.
        """
        def take_screenshot_quit():
            self.screenshot('Home')
            self.quit()

        def check_home():
            self.guiUtility.ShowPage('home')
            self.CallConditional(20, lambda: len(self.guiUtility.frame.home.aw_panel.list.GetItems()) == 1,
                                 take_screenshot_quit, "No thumbnail torrent in Home panel")

        def added_rss():
            self.screenshot('Rssfeed added')

            # switch to files tab
            mt_index = self.managechannel.GetPage(self.managechannel.notebook, "Manage torrents")
            self.managechannel.notebook.SetSelection(mt_index)

            managefiles = self.managechannel.fileslist
            self.CallConditional(
                60, lambda: len(managefiles.GetItems()) > 0, check_home, 'Channel did not have torrents')

        def do_rss():
            self.managechannel.rss_url.SetValue(os.path.join(self.session_base_dir, 'test_rss.xml'))
            self.managechannel.OnAddRss()

            # switch to manage tab
            m_index = self.managechannel.GetPage(self.managechannel.notebook, "Manage")
            self.managechannel.notebook.SetSelection(m_index)

            self.callLater(1, added_rss)

        def do_create():
            self.screenshot('After selecting mychannel page')

            self.managechannel = self.frame.managechannel

            self.managechannel.name.SetValue('UNITTEST')
            self.managechannel.description.SetValue('Channel created for UNITTESTING purposes')

            self.managechannel.Save()
            self.screenshot('After clicking save')

            self.CallConditional(60, lambda: self.frame.managechannel.channel and self.frame.managechannel.rss_url,
                                 do_rss, 'Channel instance did not arrive at managechannel')

        def do_page():
            self.guiUtility.ShowPage('mychannel')
            self.callLater(1, do_create)

        self.startTest(do_page)

    def startTest(self, callback):

        def get_and_modify_dispersy():
            from Tribler.dispersy.endpoint import NullEndpoint

            self._logger.debug("Frame ready, replacing dispersy endpoint")
            dispersy = self.session.get_dispersy_instance()
            dispersy._endpoint = NullEndpoint()
            dispersy._endpoint.open(dispersy)

            callback()

        TestGuiAsServer.startTest(self, get_and_modify_dispersy)

    def createTorrent(self):
        tdef = TorrentDef()
        tdef.add_content(os.path.join(TESTS_DATA_DIR, "video.avi"))
        tdef.set_tracker("http://localhost/announce")
        tdef.finalize()
        torrentfn = os.path.join(self.session.get_state_dir(), "gen.torrent")
        tdef.save(torrentfn)

        self._torrent_info_hash = tdef.get_infohash()

        return torrentfn
