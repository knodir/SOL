from sol.topology.resource import Resource, CompoundResource
from sol.utils.pythonHelper import listEq

cdef class Path:
    """ Represents a path in the network"""

    cdef public int _ID
    cdef public double _numFlows
    cdef public _nodes
    cdef _links

    # def __cinit__(self, nodes, ID, numFlows=0):
    #     self._numFlows = numFlows
    #     self._ID = ID
    #     self._nodes = nodes

    def __init__(self, nodes, ID, numFlows=0):
        """Create a new path

        :param nodes: a list of node ids that belong to a path
        :param numFlows: the number of flows on this path
        """
        self._nodes = list(nodes)
        self._numFlows = numFlows
        self._ID = ID
        self._links = self._computeLinks()

    @staticmethod
    def decode(dictionary):
        """
        Create a new path from a dict
        :param dictionary: dict type, must contain following keys:

            'nodes': maps to a list of nodes
        """
        return Path(dictionary['nodes'], dictionary.get('numFlows', 0))

    cpdef getIngress(self):
        """
        :return: the ingress node of this path
        """
        return self._nodes[0]

    cdef _computeLinks(self):
        return zip(self._nodes, self._nodes[1:])

    cpdef getEgress(self):
        """
        :return: the egress node of this path
        """
        return self._nodes[-1]

    cpdef getNodes(self):
        """
        :return: all nodes as a list
        """
        return self._nodes

    cpdef getNodesAsTuple(self):
        """
        :return: all nodes in this path as a tuple
        """
        return tuple(self._nodes)

    cpdef getIEPair(self):
        """
        :return: ingress-egress pair for this path
        :rtype: tuple
        """
        return self.getIngress(), self.getEgress()

    cpdef double getNumFlows(self):
        """
        :return: the number of flows on this path.
        """
        return self._numFlows

    cpdef setNumFlows(self, double nflows):
        """
        Set number of flows on this path

        :param nflows: the new number of flows
        """
        self._numFlows = nflows

    cpdef getLinks(self):
        """
        :return: Return an iterator over the links in this path
        """
        # return zip(self._nodes, self._nodes[1:])
        return self._links

    cpdef int getID(self):
        return self._ID

    def encode(self):
        """
        Encode this path in dict/list form so it can be JSON-ed or MsgPack-ed

        :return: dictionary representation of this path
        """
        return {'nodes': self._nodes, 'numFlows': self._numFlows}

    def hasResource(self, res, topo):
        if isinstance(res, Resource):
            nodeset = self._nodes
            linkset = self.getLinks()
        elif isinstance(res, CompoundResource):
            nodeset = frozenset(self._nodes).intersection(res.nodes)
            linkset = frozenset(self.getLinks()).intersection(res.links)
        return any([res.name in topo.getResources(n) for n in nodeset]) or \
               any([res.name in topo.getResources(l) for l in linkset])

    def __iter__(self):
        return self._nodes.__iter__()

    def __len__(self):
        return len(self._nodes)

    def __repr__(self):
        return "Path(nodes={}, numFlows={})".format(str(self._nodes),
                                                    self._numFlows)

    # def __eq__(self, other):
    #     if isinstance(other, Path):
    #         return self._nodes == other._nodes
    #     else:
    #         return False

    def __richcmp__(Path self, Path other not None, int op):
        if op == 2:
            return listEq(self._nodes, other._nodes)
        elif op == 3:
            return listEq(self._nodes, other._nodes)
        else:
            raise TypeError


# TODO: move this to cdef
class PathWithMbox(Path):
    """
    Create a new path with middlebox

    :param nodes: path nodes (an ordered list)
    :param useMBoxes: at which nodes the middleboxes will be used
    :param numFlows: number of flows (if any) along this path. Default is 0.
    """

    def __init__(self, nodes, int ind, useMBoxes, numFlows=0):
        super(PathWithMbox, self).__init__(nodes, ind, numFlows)
        self.useMBoxes = list(useMBoxes)

    @staticmethod
    def decode(dictionary):
        """
        Create a new path from a dict
        :param dictionary: dict type, must contain following keys:

            'nodes': maps to a list of nodes
            'useMBoxes': maps to a list of nodes at which middlebox is used
        """
        return PathWithMbox(dictionary['nodes'], dictionary['useMBoxes'], dictionary.get('numFlows', 0))

    def usesBox(self, node):
        """
        Check the path uses a given middlebox

        :param node: nodeID in question
        :return: True or False
        """
        return node in self.useMBoxes

    def fullLength(self):
        """

        :return: The full length of the path (includes all middleboxes)
        """
        return len(self._nodes) + len(self.useMBoxes)

    def encode(self):
        """
        Encode this path in dict/list form so it can be JSON-ed or MsgPack-ed

        :return: dictionary representation of this path
        """
        return {'nodes': self._nodes, 'numFlows': self._numFlows, 'useMBoxes': self.useMBoxes,
                'PathWithMbox': True}

    def __key(self):
        return tuple(self._nodes), tuple(self.useMBoxes), self._numFlows

    def __eq__(self, other):
        if not isinstance(other, PathWithMbox):
            return False
        return listEq(self._nodes, other._nodes) and listEq(self.useMBoxes, other.useMBoxes)

    def __repr__(self):
        return "PathWithMbox(nodes={}, useMBoxes={} numFlows={})". \
            format(str(self._nodes), self.useMBoxes, self._numFlows)