from Tribler.community.tunnel.hidden_community import HiddenTunnelCommunity
from Tribler.community.tunnel.tunnel_community import Circuit, RelayRoute, TunnelExitSocket
from Tribler.community.multichain.community import MultiChainCommunity


class HiddenTunnelCommunityMultichain(HiddenTunnelCommunity):

    def __init__(self, *args, **kwargs):
        super(HiddenTunnelCommunityMultichain, self).__init__(*args, **kwargs)
        self.multichain_community = None
        self.get_multichain_community()

    @classmethod
    def get_master_members(cls, dispersy):
        # generated: Thu May 26 17:04:23 2016
        # curve: None
        # len: 571 bits ~ 144 bytes signature
        # pub: 170 3081a7301006072a8648ce3d020106052b81040027038192000404363b98b8145f66d0b74136fdb1d3699
        #          bdb62d394417f10b3be31d94ac3779261e26b9dde1416362a021dbdfbc5616e88b8bd0fb6e924e893a199
        #          2f53498c4086b96fae02f9e78c00064b92ceea9c97cbb6207bffce9646978a6766d46cf0a1c3629c92822
        #          2bd6e00adb43344ac4196bca72b03ddac18d69d184e99186da07ceab2953d30fef30bff2d4752abfcb7ca
        # pub-sha1 5427ee66bcdbcc767b21600ec0db4c3cd96eba02
        # -----BEGIN PUBLIC KEY-----
        # MIGnMBAGByqGSM49AgEGBSuBBAAnA4GSAAQENjuYuBRfZtC3QTb9sdNpm9ti05RB
        # fxCzvjHZSsN3kmHia53eFBY2KgIdvfvFYW6IuL0Ptukk6JOhmS9TSYxAhrlvrgL5
        # 54wABkuSzuqcl8u2IHv/zpZGl4pnZtRs8KHDYpySgiK9bgCttDNErEGWvKcrA92s
        # GNadGE6ZGG2gfOqylT0w/vML/y1HUqv8t8o=
        # -----END PUBLIC KEY-----
        master_key = "3081a7301006072a8648ce3d020106052b81040027038192000404363b98b8145f66d0b74136fdb1d3699" + \
                  "bdb62d394417f10b3be31d94ac3779261e26b9dde1416362a021dbdfbc5616e88b8bd0fb6e924e893a199" +\
                  "2f53498c4086b96fae02f9e78c00064b92ceea9c97cbb6207bffce9646978a6766d46cf0a1c3629c92822" + \
                  "2bd6e00adb43344ac4196bca72b03ddac18d69d184e99186da07ceab2953d30fef30bff2d4752abfcb7ca"
        master_key_hex = master_key.decode("HEX")
        master = dispersy.get_member(public_key=master_key_hex)
        return [master]

    def get_multichain_community(self):
        try:
            self.multichain_community = next((c for c in self.dispersy.get_communities() if isinstance(c, MultiChainCommunity)))
        except StopIteration:
            self.multichain_community = None

    def increase_bytes_sent(self, obj, num_bytes):
        self.increase_bytes_pending(obj, num_bytes, 0)
        super(HiddenTunnelCommunityMultichain, self).increase_bytes_sent(obj, num_bytes)

    def increase_bytes_received(self, obj, num_bytes):
        self.increase_bytes_pending(obj, 0, num_bytes)
        super(HiddenTunnelCommunityMultichain, self).increase_bytes_received(obj, num_bytes)

    def increase_bytes_pending(self, obj, delta_up, delta_down):
        # Make sure we have found the multichain community, or find it now
        if not self.multichain_community:
            self.get_multichain_community()
            if not self.multichain_community:
                # If we cannot find the multichain community when increase_bytes_sent is called,
                # we have a problem, as these bytes cannot be accounted for
                print "BYTES, but no multichain"
                return

        # Find the public key of the relevant peer
        if isinstance(obj, Circuit):
            key = obj.mid
        elif isinstance(obj, RelayRoute):
            key = self.circuits[obj.circuit_id].mid
        elif isinstance(obj, TunnelExitSocket):
            key = self.circuits[obj.circuit_id].mid
        else:
            print "This is not a proper thingy"
            return

        self.multichain_community.increase_bytes_pending(key, delta_up, delta_down)





