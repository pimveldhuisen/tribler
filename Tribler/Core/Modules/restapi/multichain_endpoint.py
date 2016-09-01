import json
import base64

from twisted.web import http, resource

from Tribler.community.multichain.community import MultiChainCommunity


class MultichainEndpoint(resource.Resource):
    """
    This endpoint is responsible for handing requests for multichain data.
    """

    def __init__(self, session):
        resource.Resource.__init__(self)

        child_handler_dict = {"statistics": MultichainStatsEndpoint, "score": MultichainScoreEndpoint}

        for path, child_cls in child_handler_dict.iteritems():
            self.putChild(path, child_cls(session))


class MultichainStatsEndpoint(resource.Resource):
    """
    This class handles requests regarding the multichain community information.
    """

    def __init__(self, session):
        resource.Resource.__init__(self)
        self.session = session

    def get_multichain_community(self):
        """
        Search for the multichain community in the dispersy communities.
        """
        for community in self.session.get_dispersy_instance().get_communities():
            if isinstance(community, MultiChainCommunity):
                return community
        return None

    def render_GET(self, request):
        """
        .. http:get:: /multichain/statistics

        A GET request to this endpoint returns statistics about the multichain community

            **Example request**:

            .. sourcecode:: none

                curl -X GET http://localhost:8085/multichain/statistics

            **Example response**:

            .. sourcecode:: javascript

                {
                    "statistics":
                    {
                        "self_id": "TGliTmFDTFBLO...VGbxS406vrI=",
                        "latest_block_insert_time": "2016-08-04 12:01:53",
                        "self_total_blocks": 8537,
                        "latest_block_id": "Sv03SmkiuL+F4NWxHYdeB6PQeQa/p74EEVQoOVuSz+k=",
                        "latest_block_requester_id": "TGliTmFDTFBLO...nDwlVIk69tc=",
                        "latest_block_up_mb": "19",
                        "self_total_down_mb": 108904,
                        "latest_block_down_mb": "0",
                        "self_total_up_mb": 95138,
                        "latest_block_responder_id": "TGliTmFDTFBLO...VGbxS406vrI="
                    }
                }
        """
        mc_community = self.get_multichain_community()
        if not mc_community:
            request.setResponseCode(http.NOT_FOUND)
            return json.dumps({"error": "multichain community not found"})

        return json.dumps({'statistics': mc_community.get_statistics()})


class MultichainScoreEndpoint(resource.Resource):
    """
    This class handles requests for the score of a certain multichain community member.
    """

    def __init__(self, session):
        resource.Resource.__init__(self)
        self.session = session

    def get_multichain_community(self):
        """
        Search for the multichain community in the dispersy communities.
        """
        for community in self.session.get_dispersy_instance().get_communities():
            if isinstance(community, MultiChainCommunity):
                return community
        return None

    def render_GET(self, request):
        """
        .. http:get:: /multichain/score?k=(string: hex encoded public_key)

        A GET request to this endpoint returns the score for a certain public key from the POV of this node

            **Example request**:

            .. sourcecode:: none

                curl -X GET http://localhost:8085/multichain/score?k=4C69624E61434C504B3ACC9E30D50423095A998915BC765194341346EBFB494B6E209808F086BE9F7B0CE04FACDA562BDD3EDF49EA803FFC8B4264BB429B85D994F47AF48D70242CCCA0

            **Example response**:

            .. sourcecode:: javascript

                {
                    "score": 100
                }
        """
        mc_community = self.get_multichain_community()
        if not mc_community:
            request.setResponseCode(http.NOT_FOUND)
            return json.dumps({"error": "multichain community not found"})

        if 'k' not in request.args:
            request.setResponseCode(http.BAD_REQUEST)
            return json.dumps({"error": "public key parameter missing"})

        public_key = request.args['k'][0]
        print public_key
        return json.dumps({'score': mc_community.get_score(public_key.decode("HEX"))})
