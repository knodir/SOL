# coding=utf-8

import functools
import itertools
import pprint
from random import shuffle

import networkx

from sol.opt.funcs import defaultLinkFunc
from sol.path.predicates import useMboxModifier

from sol.opt import getOptimization, initOptimization
from sol.topology import provisioning
from sol.topology.provisioning import generateTrafficClasses

from sol.path import chooserand
from sol.path import generatePathsPerTrafficClass
from sol.topology import Topology, TrafficMatrix

if __name__ == '__main__':

    # Let's create our topology first, as an example
    # ============================================
    topo = Topology('Abilene', 'data/topologies/Abilene.graphml')
    # print("topo.name %s\ntopo.nodes: %s\n\n" % (topo.name, topo.nodes()))

    # Let's load an existing gravity traffic matrix. It's just a dict mapping ingress-egress tuples to flow volume (a float).
    trafficMatrix = TrafficMatrix.load('data/tm/Abilene.tm')
    # set nodes to be firewalls and IDSes:
    for node in topo.nodes():
        topo.setMbox(node)
        topo.setServiceTypes(node, ['fw', 'ids'])
        print("topo.getServiceTypes(): %s\n" % topo.getServiceTypes(node))

    trafficClasses = generateTrafficClasses(trafficMatrix.keys(), trafficMatrix, {'allTraffic': 1},
                                            {'allTraffic': 2000})
    print("trafficMatrix.keys(): %s\n" % trafficMatrix.keys())

    # assign flow processing cost for each traffic class
    for t in trafficClasses:
        t.cpuCost = 10
        print("\ntrafficClass: %s" % t)
        print("trafficClass.volBytes: %s" % t.volBytes)
        print("trafficClass.volFlows: %s" % t.volFlows)

    # Do some topology provisioning, instead of the real switch/link/middlebox capacities:
    # provision the node cpu capacities (for the sake of example)
    maxCPUCap = provisioning.computeMaxIngressLoad(trafficClasses, {t: t.cpuCost for t in trafficClasses})
    print("maxCPUCap: %d\n" % maxCPUCap)
    nodeCaps = dict()
    # we assign equal compute capacity to all switches. The value is the maximum
    # number of CPUs required to handle flows. For this, we look at each node
    # (switch), extract number of flows passing that node (looking at the
    # tc.volFlows which is equal to the traffic matrix value at .tm input file) 
    # and multiply it with the CPU cost associated with each flow (cpuCost=10 in
    # this case). We sum this multiplication result for each flow and get a
    # single maximum value which is assigned as the CPU of each node. In fact,
    # we multiply this max value to 2 (see below), which I believe represents
    # chain length, i.e., fw and ids will consume double amount if the max CPU.
    # This essentially means switches are never CPU saturated (is it true?).
    nodeCaps['cpu'] = {node: maxCPUCap * 2 for node in topo.nodes()
                       if 'fw' or 'ids' in topo.getServiceTypes(node)}
    print("nodeCaps: %s\n" % nodeCaps)

    # provision the TCAM capacities on the switch nodes
    # in this example, all switches have equal TCAM space of 1000.
    nodeCaps['tcam'] = {node: 1000 for node in topo.nodes()}
    print("nodeCaps: %s\n" % nodeCaps)

    # similartly with link capacities
    # we do CPU-like computation for linkCaps (see more elaborate description
    # above, the one for nodeCaps). Essentially, all linkCaps have the same
    # value and it is the maximum link capacity required to handle the entire
    # flow.
    linkCaps = provisioning.provisionLinks(topo, trafficClasses, 3)
    print("linkCaps: %s\n" % linkCaps)


    # =====================================
    # Write our user defined capacity functions
    # =====================================

    def path_predicate(path, topology):
        # Firewall followed by IDS is the requirement for the path to be valid
        # print("path: %s\ntopology: %s" % (path, topology))
        # print("topology.getServiceTypes: %s" % (topology.getServiceTypes()))
        return any([s == ('fw', 'ids') for s in itertools.product(*[topology.getServiceTypes(node)
                                                                    for node in path.useMBoxes])])


    def nodeCapFunc(node, tc, path, resource, nodeCaps):
        # this computes the cost of processing the traffic class at a given node
        if resource == 'cpu' and node in nodeCaps['cpu']:
            return tc.volFlows * tc.cpuCost / nodeCaps[resource][node]
        else:
            raise ValueError("wrong resource")  # just in case

    def linkCapFunc(link, tc, path, resource, linkCaps):
        print("tc.name %s, tc.volBytes: %d" % (tc.name, tc.volBytes))
        print("linkCaps[link]: %d" % linkCaps[link])
        print("result: %f" % (tc.volBytes / linkCaps[link]))
        return tc.volBytes / linkCaps[link]

    # Curry the functions to conform to the required signature
    nodeFunc = functools.partial(nodeCapFunc, nodeCaps=nodeCaps)
    linkFunc = functools.partial(linkCapFunc, linkCaps=linkCaps)

    def TCAMCapFunc(node, tc, path, resource):
        # it would be best to test if node is a switch here, but we know all nodes are switches in this example
        if resource == 'tcam':
            return 2  # two rules per path on each switch, just as an example.
        else:
            raise ValueError("wrong resource")  # just in case


    # ======================
    # start our optimization
    # ======================
    # Get paths that conform to our path predicate, choose a subset of 5 randomly to route traffic on.
    # pptc = Path Per Traffic Class
    opt, pptc = initOptimization(topo, trafficClasses, path_predicate,
                                 'random', 5, functools.partial(useMboxModifier, chainLength=2), 'CPLEX')

    # Allocate and route all of the traffic
    opt.allocateFlow(pptc)
    opt.routeAll(pptc)

    # We know that we will need binary variables per path and node to model TCAM constraints
    opt.addBinaryVars(pptc, topo, ['path', 'node'])
    # Add TCAM capacities here
    opt.capNodesPathResource(pptc, 'tcam', nodeCaps['tcam'], TCAMCapFunc)

    # Now just add constraints for link capacities (use default Link Function, nothing fancy here)
    opt.capLinks(pptc, 'bandwidth', linkCaps, linkFunc)
    # And similarly node capacities
    # Recall that we are normalizing the CPU node load to [0, 1], so capacities are now all 1.
    opt.capNodes(pptc, 'cpu', {node: 1 for node in topo.nodes()
                               if 'fw' or 'ids' in topo.getServiceTypes(node)}, nodeFunc)

    # Finally, the objective, minimize the load on the middleboxes
    opt.minNodeLoad(pptc, 'cpu')

    # Solve the formulation:
    # ======================
    opt.solve()

    # Print the objective function --- in this case the load on the maximally loaded middlebox [0, 1]
    print("objective: %f" % opt.getSolvedObjective())
    # pretty-print the paths on which the traffic is routed, along with the fraction for each traffic class
    # useMBoxes indicates at which middleboxes the processing should occur
    for tc, paths in opt.getPathFractions(pptc).iteritems():
        print 'src:', tc.src, 'dst:', tc.dst, 'paths:', pprint.pformat(paths)
    print("len(opt.getPathFractions()): %d" % len(opt.getPathFractions(pptc)))
