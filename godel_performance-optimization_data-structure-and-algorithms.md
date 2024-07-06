# Gödel Scheduler Performance Optimization: Algorithm Design Ideas and Data Structure Applications

> Based on its excellent scheduling performance, [Gödel Scheduler](https://github.com/kubewharf/godel-scheduler/) has the ability to run stably for a long time under ultra-large cluster scales (20k+ Nodes, 1000k+ Pods), ultra-high business workloads (1k+ Incoming Pods/s), and extremely complex scenarios (Machine Learning / Batch / Streaming / Tidal Hybrid Deployment, etc.).

[Gödel Scheduler](https://github.com/kubewharf/godel-scheduler/) is ByteDance's open source unified online and offline scheduler, which aims to use the same set of schedulers to uniformly schedule and manage online/offline services and realize resource pooling, thereby improving resource utilization and resource elasticity while optimizing business costs and experience and reducing operation and maintenance pressure.

Currently, the single-shard scheduling throughput of [Gödel Scheduler](https://github.com/kubewharf/godel-scheduler/) can reach **2500+ Pods/s (10x Kube Scheduler)**, and the multi-shard scheduling throughput can reach **5000+ Pods/s**, which is inseparable from a lot of creative ideas.

This article will take several classic optimizations as examples to explain the algorithm design ideas and data structure applications derived from these ideas, and explain their great role in improving the scheduling performance of [Gödel Scheduler](https://github.com/kubewharf/godel-scheduler/) and ultimately solving practical problems.

## 1. Incremental Update

### Introducetion

Similar to Kube Scheduler, [Gödel Scheduler](https://github.com/kubewharf/godel-scheduler/) also maintains In-Memory `Cache` and `Snapshot`.

Cache:

- Maintaining the organizational relationship of various Resource Objects helps to quickly obtain aggregate information (such as the total amount of resources used by a node) and improve the execution efficiency of the scheduling algorithm

- Real-time changes will be triggered by Events, and data maintenance requires locking the entire Cache

Snapshot:

- Avoid the impact of Events during the current scheduling round and ensure data consistency during the scheduling process

- Data is read-only during a single scheduling round and does not require locking

At the beginning of each scheduling process, the latest data in the Cache needs to be synchronized and cloned to the Snapshot for use by the serial scheduling process, so the efficiency of data synchronization is particularly critical.

### Problem and Solution

Compared with Kube Scheduler, [Gödel Scheduler](https://github.com/kubewharf/godel-scheduler/) has more complex scheduling features and needs to carry larger clusters and applications, which brings more types of cache information and larger data synchronization scales. Previously, with the natural growth of business workloads and cluster scale, a large number of production clusters frequently encountered performance problems caused by full cloning of various cache information, which seriously dragged down scheduling throughput and scheduling latency.

❓ Thinking:

In the time interval between two scheduling rounds, not all data units in the cache have changed; in fact, we only need to identify the changed parts and overwrite them in the form of "increments" to the Snapshot of the previous scheduling to meet the data synchronization requirements.

Specifically:

1. Assume that in the previous round of scheduling, Snapshot has completely copied `Node 0`, `Node 1`, ..., `Node 5` in the Cache. When the current scheduling round is initiated, `Node 1` & `Node 3` in the Cache are updated, `Node 5` is deleted, and `Node 6` is added. How should Snapshot perceive this?
   
   ![1_generation_1](https://raw.githubusercontent.com/BinacsLee/blog/main/img/godel_performance-optimizaion/1_generationstore_1.excalidraw.png)
   
   Obviously, without special maintenance, it is difficult for Snapshot to know what changes have occurred in the Cache from a certain moment unless all objects are traversed and compared.

2. If we manually assign a specific `generation` to each object and maintain the object list in descending order, then cache changes within a continuous period of time can be mapped to a continuous period of time. The global `generation` value corresponding to the previous round of scheduling is used as the baseline, and all objects that are currently greater than the global `generation` value are "increments" to the baseline.
   
   ![1_generation_2](https://raw.githubusercontent.com/BinacsLee/blog/main/img/godel_performance-optimizaion/1_generationstore_2.excalidraw.png)

   All objects are organized in chronological order, and the global `generation` value `(x+5)` of the previous round is recorded in the Snapshot. The `generation` values ​​of objects that subsequently change will be greater than the baseline value, so that the "increment" can be perceived and local updates can be performed.

3. The above data maintenance process is further abstracted: in essence, what needs to be exposed to the upper layer in Cache and Snapshot is a storage (GenerationStore) that can provide `Get` & `Set` interfaces; the difference is that the storage of Cache `ListStore` needs to be able to maintain time sequence internally, while Snapshot `RawStore` only cares about the storage object itself.
   
   ![1_generation_3](https://raw.githubusercontent.com/BinacsLee/blog/main/img/godel_performance-optimizaion/1_generationstore_3.excalidraw.png)

Through logical abstraction and comprehensive access to all types of data for incremental updates, the data synchronization cost of cached information is greatly reduced, the scheduling throughput is significantly improved, and the scheduling delay is optimized.

As shown in the figure below, the overall e2e scheduling delay has dropped from minutes to milliseconds and remains stable in the long term, with an optimization of 4 orders of magnitude.

![1_img_1](https://raw.githubusercontent.com/BinacsLee/blog/main/img/godel_performance-optimizaion/1_img_1.png)

![1_img_2](https://raw.githubusercontent.com/BinacsLee/blog/main/img/godel_performance-optimizaion/1_img_2.png)

## 2. Discretization Node List

### Introducetion

For scheduling efficiency considerations, a single Pod will not traverse all feasible nodes in the cluster when scheduling, but will stop immediately after traversing a specific number or a specific proportion. Therefore, the scheduling of each Pod has a certain spatial locality.

Under this premise, in order to try to achieve natural discreteness during scheduling, the original logic will maintain a `NodeTree` (two-dimensional array) according to the topological domain. When updating the Snapshot, the `NodeTree` will be compressed into a one-dimensional list and stored in the Snapshot, and it will be used in a modulo rotation form during each scheduling.

![2_nodeslice_nodetree](https://raw.githubusercontent.com/BinacsLee/blog/main/img/godel_performance-optimizaion/2_nodeslice_nodetree.excalidraw.png)

### Problem and Solution

It is not difficult to see that there are obvious problems in the generation process of the above `NodeList`: the NodeList constructed by flattening the `NodeTree` is not truly discrete at the topological domain level. It can only ensure that the front part of each Zone is evenly distributed, while the back part will be completely occupied by a large number of nodes in the same Zone, causing some Pods to easily generate topological domains by mistake.

The more serious problem is that the `NodeList` will frequently trigger the complete reconstruction of the entire list due to scenarios such as the `Add` / `Delete` of any Node, and the reconstruction process needs to traverse the entire node storage and trigger memory allocation and recycling. In a large-scale cluster of 20k+ Nodes, the incoming workload is close to 1k Pods/s, and the computational overhead of frequently rebuilding the NodeList reaches **50+%** of the overall process overhead, seriously affecting the scheduling efficiency.

❓ Thinking:

1. How to achieve true topological domain discretization?
   
   > It is equivalent to completely randomizing the subscript position of any node in `NodeList`

2. How to avoid the overhead of frequent reconstruction and maintain NodeList at low cost?
   
   > Ideally, the addition and deletion of a single element should be completed within the time complexity of $O(1)$
   > 
   > - Add: directly append to the end of the linear list
   > 
   > - Delete: swap the element to be deleted with the element at the end of the list, and then remove the last element (at this time, HashMap needs to be combined to implement element subscript indexing to support element exchange)
   > 
   > - Update: delete + add


![2_nodeslice_hashslice](https://raw.githubusercontent.com/BinacsLee/blog/main/img/godel_performance-optimizaion/2_nodeslice_hashslice.excalidraw.png)

Due to the randomness of `Add` / `Delete` / `Update` of all nodes in the entire cluster, it is easy to know that the node corresponding to any subscript element in `NodeList` is completely random; further, the node corresponding to each subscript in a continuous interval of any length is random, then the mathematical expectation of the proportion of any topological domain in the continuous interval is consistent with its global statistical proportion, which can ensure the discretization of the topological domain.

By redesigning the NodeList maintenance mechanism, we solved the performance problems of multiple ultra-large-scale production clusters and achieved better node discretization with lower overhead.

As shown in the figure below, after the upgrade in the afternoon of October 11, 2022, the main heat distribution of the overall e2e scheduling delay dropped from minutes to milliseconds.

![2_img_1](https://raw.githubusercontent.com/BinacsLee/blog/main/img/godel_performance-optimizaion/2_img_1.png)

![2_img_2](https://raw.githubusercontent.com/BinacsLee/blog/main/img/godel_performance-optimizaion/2_img_2.png)

## 3. Heuristic Pruning Algorithm

### Introducetion

In Gödel Scheduler, the scheduling of a single Unit is divided into two stages: `Scheduling` + `Preempting`. When a Pod cannot be placed on a specific node under the normal Scheduling Filter mechanism, preemption will be triggered through Preempting, and the purpose of scheduling will be achieved by trying to evict some Pods.

The preemption process requires a lot of calculation logic to make decisions on *"which Node to preempt"* and *"which Pods to evict"*, so it has always been a CPU hotspot in some scheduling scenarios. The essence of preemption is actually a search tree, and its main process is as follows:

![3_preemption_intro](https://raw.githubusercontent.com/BinacsLee/blog/main/img/godel_performance-optimizaion/3_preemption_intro.excalidraw.png)

### Problem and Solution

In a large-scale production environment, online business workloads have obvious tidal characteristics. We will mix high-priority online businesses workloads with low-priority offline workloads in the same resource pool, and dynamically adjust the scale of offline operations as online businesses workloads expand and contract, thereby ensuring all-weather resource utilization.

When high-priority online businesses return to the field, due to the high overall resource level, they will have to initiate preemption of low-priority tasks that previously occupied cluster resources, resulting in an extremely high preemption frequency in a short period of time, which seriously drags down performance and affects the efficiency of online return.

❓ Thinking:

Assuming that the calculation logic cannot be changed, how to reduce the size of the data involved in the calculation?

1. How to reduce the size of Pods involved in computing logic?
   
   Considering that Pod `Priority` is the basic principle of preemption, the existing Pods on the node can be classified and sorted in advance. For the Pod to be scheduled currently, the maximum number of Pods that it can preempt is determined, and the number of Pods that need to be considered can be greatly reduced.

   ![3_preemption_pods](https://raw.githubusercontent.com/BinacsLee/blog/main/img/godel_performance-optimizaion/3_preemption_pods.excalidraw.png)

2. How to reduce the size of the Node involved in the calculation logic?
   
   💡 An assumption: Can we make a rough estimate of "whether preemption can be successful" before entering the complex calculation logic?
   
   Optimistically assuming that the current Pod can preempt all Pods with lower priority (in fact, some Pods may not be preempted due to rules such as PDB protection), the total amount of resources that can be released is clear. If there is a way to obtain this part of the releasable resources and add it to the remaining resources of the node, the total amount of resources that the current Pod can use in the case of preemption can be obtained. If the total amount still does not meet the Pod Request, then the preemption behavior of the current node must fail (heuristic pruning).
   
   💡 Going further: How to quickly obtain the amount of releasable resources on the node for the current Pod to be scheduled?
   
   Based on the premise that the Pods on the node have been sorted by Priority, if the prefix sum of the resource dimension can be recorded for each position, then for the specific Priority of the current Pod to be scheduled, as long as the last position with a priority less than the Priority is found, the prefix sum of the position is what is required.
   
   🥊 Challenge: Pods on the node will be dynamically added and deleted at a very high frequency. How to maintain the ordered structure and resource prefix sum at a low cost?
   
   We can break it down into two sub-problems:
   
   - Maintain orderliness: Balanced Binary Search Tree
   
   - Maintain resource prefix sum: Abstract the [prefix sum problem] into an [interval sum problem], and then transform the [linear interval sum] into a [structured subtree sum]. With Splay-Tree, it is possible to maintain the subtree property (resource dimension sum) while maintaining orderliness, and dynamically adjust the tree structure through Splay stretching operations, and obtain the required prefix sum through subtree sum.
   
   ![3_preemption_nodes](https://raw.githubusercontent.com/BinacsLee/blog/main/img/godel_performance-optimizaion/3_preemption_nodes.excalidraw.png)

3. The final effect: efficient pruning is achieved on the search tree.
   
   ![3_preemption_final](https://raw.githubusercontent.com/BinacsLee/blog/main/img/godel_performance-optimizaion/3_preemption_final.excalidraw.png)

Based on the multi-dimensional pruning strategy of `Pod` & `Nodes`, we can quickly recover the preemption throughput, significantly reduce the preemption latency, and quickly filter out situations where preemption is not possible within 2ms.

![3_img_1](https://raw.githubusercontent.com/BinacsLee/blog/main/img/godel_performance-optimizaion/3_img_1.png)

![3_img_2](https://raw.githubusercontent.com/BinacsLee/blog/main/img/godel_performance-optimizaion/3_img_2.png)

## Achievements and Future Plans

Based on the aforementioned multiple designs and optimizations, [Gödel Scheduler](https://github.com/kubewharf/godel-scheduler/) has achieved great breakthroughs in scheduling throughput in general scenarios. At present, the single-shard [Gödel Scheduler](https://github.com/kubewharf/godel-scheduler/) can handle most of ByteDance's business scenarios with ease, and multi-sharding can also provide longer-term stable business load processing capabilities.

In addition, [Gödel Scheduler](https://github.com/kubewharf/godel-scheduler/) has also made a lot of creative design optimizations for multiple segmented scenarios such as high water levels of cluster resources and achieved significant benefits. We will gradually migrate these optimizations to the open source version in the future.

# \* Ref

- [Gödel Scheduler 性能优化: 算法设计思想与数据结构应用](https://mp.weixin.qq.com/s/xEYR_vC9LDaka9-EwalqcA)

- [Gödel: Unified Large-Scale Resource Management and Scheduling at ByteDance](https://dl.acm.org/doi/abs/10.1145/3620678.3624663)

- [kubewharf/godel-schedulere](https://github.com/kubewharf/godel-scheduler/)