>   Session: https://kccncossaidevchn2024.sched.com/event/1eYWt/how-to-increase-the-throughput-of-kubernetes-scheduler-by-tens-of-times-kuberneteshoy-jzha-hao-pan-yuquan-ren-bing-li-bytedance?iframe=no
> 
>   Recording: https://www.youtube.com/watch?v=_ayPdIVs_SI

# How to Increase the Throughput of Kubernetes Scheduler by Tens of Times

## P1 KubeCon China 2024

![P1](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P1.png)

## P2 (Title) How to Increase the Throughput of Kubernetes Scheduler by Tens of Times

![P2](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P2.png)

## P3 Introduction

![P3](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P3.png)

## P4 Background - Kubernetes Scalability

![P4](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P4.png)

About [Kubernetes Scalability Thresholds](https://github.com/kubernetes/community/blob/master/sig-scalability/configs-and-limits/thresholds.md).

> PS: There is a lot of debate on whether to choose one large cluster or more small clusters.
> 
> In fact, both methods have their limitations and advantages.
> 
> For ByteDance, the maintenance complexity and user isolation of large clusters can be overcome. For details, please refer to the open source projects of [KubeWharf](https://github.com/kubewharf)
> 
> We are more concerned about reducing the maintenance burden and achieving **higher resource utilization** through large clusters.

> One more thing, large-scale training workloads will inevitably require large clusters...
> 
> Currently, the largest single cluster manages more than **70,000 GPUs** and achieves **95%+** GPU utilization.

## P5 Background - Kubernetes Scheduler

![P5](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P5.png)

Kubernetes Scheduler is monolithic in architecture, which constrains its performance ceiling.

In terms of detailed implementation, Scheduler consists of at least four core modules:

1. **SchedulingQueue** senses the workloads (Pods) to be scheduled through the events mechanism and queues them internally, waiting to be scheduled.
2. **Cache** build the cluster in memory through the events mechanism, and also contains records of temporary memory operations. Cache often aggregates and preprocesses data on native objects.
3. **Snapshot** is a data snapshot of Cache at the start of scheduling to ensure data consistency in the scheduling process.
4. **Workflow** (including scheduling and preemption) as the part that actually makes decisions, gets the workload (Pod) that is queued at the top of the SchedulingQueue and selects the most suitable node based on its scheduling semantics. When there is no feasible result, it releases resources from the cluster by preemption to achieve scheduling placement. In general, the workflow includes three stages: **scheduling**, **preemption**, and **binding** (asynchronous). Here we only care about scheduling and preemption, which have heavier computational overhead.

> It should be noted that hotspots may not apparent in small clusters, but in large-scale clusters, these hotspots are magnified by hundreds or even thousands of times, necessitating optimization.

## P6 Gödel Scheduling System

![P6](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P6.png)

We will explain how to optimize performance throughput based on the experience gained in building the Gödel scheduling system

Gödel is a ***unified*** scheduling system for both online and offline workloads

It has been deployed on a large scale in ByteDance's global data centers, supporting all kinds of workloads including MicroService/BigData/ML, etc.

## P7 Gödel Scheduling System - Architecture

![P7](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P7.png)

In terms of high-level architecture, Gödel is a distributed scheduling system built on the idea of ​​optimistic concurrency, which is different from the upstream Kube Scheduler. This means that it can break the performance ceiling of the single scheduler.

Specifically, concurrency is reflected in two aspects:

1. Optimistic Concurrency Architecture

> Multi-shards Concurrency.
> 
> TODO: Link to Gödel Architecture

2. SubCluster Concurrent Scheduling

> Concurrent scheduling of BE&BE + SubCluster granularity within a single-shard instance, completely avoids interference between workloads of different resource types or different resource pools, and improves the scheduling efficiency of large-scale heterogeneous clusters.

## P8 Gödel Scheduling System - Optimizations

![P8](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P8.png)

Multi-shard parallelism is the most intuitive optimization method.

Next, let’s talk about how we can use various data structures and algorithms to optimize the performance of a single shard to the utmost.

## P9 Gödel Optimizations - Data Synchronization

![P9](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P9.png)

Cache/Snapshot has been mentioned before. At the beginning of each scheduling process, the Cache infos need to be fully synchronized to the Snapshot. The larger the data scale, the more significant the data synchronization overhead.

We hope to reduce unnecessary data copies as much as possible. In other words, we hope to transform full copies into incremental updates.

Those familiar with Kubernetes source code may know that the Kube Scheduler uses an LRU-like mechanism to maintain NodeInfo, tracking objects based on time sensitive `generation`.

For example, in the figure, assume that at a certain time point (Timestamp=X), Snapshot already contains all the Node objects in the Cache. Then, `node1` and `node3` are updated, `node5` is deleted, and `node6` is added.

Each time we operate on an object, we update its timestamp (generation).

Then, by traversing in descending order, find the object that needs to be *added* or *updated* and clone it. Finally, the object that need to be *deleted* will be found by traversing the snapshot.

> Thinking: How to reduce unnecessary object synchronization?
> 
> => Only incrementally update the parts that have changed
> 
> Then, how to quickly identify the objects that have changed?
> 
> => Maintain a time-sensitive `generation`, increment it when an update occurs, and maintain it in a specific order of `generation`.

> When the size of Snapshot is very large, we will use **divide-and-conquer algorithm** to reduce the time complexity of traversal and deletion.

> ```go
> func (s *ListStoreImpl) UpdateRawStore(store RawStore, cloneFunc CloneFunc, cleanFunc CleanFunc) {
> 	storedGeneration := store.GetGeneration()
> 	for e := s.Front(); e != nil; e = e.Next() {
> 		if e.GetGeneration() <= storedGeneration {
> 			break
> 		}
> 		cloneFunc(e.key, e.StoredObj)
> 	}
> 	store.SetGeneration(s.generation)
> 	cleanFunc()
> }
> 
> func DefaultCleanFunc(cache ListStore, snapshot RawStore) CleanFunc {
> 	return func() {
> 		if cache.Len() != snapshot.Len() {
> 			diff := snapshot.Len() - cache.Len()
> 			snapshot.ConditionRange(func(key string, _ StoredObj) bool {
> 				if diff <= 0 {
> 					// Quick break the range loop.
> 					return false
> 				}
> 				if cache.Get(key) == nil {
> 					snapshot.Delete(key)
> 					diff--
> 				}
> 				return true
> 			})
> 		}
> 	}
> }
> ```

## P10 Gödel Optimizations - Data Synchronization

![P10](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P10.png)

In fact, the objects we need to maintain are not just NodeInfo, but also various custom data structures. Therefore, we abstract and enhance the entire incremental update mechanism.

Specifically, the basic storage [GenerationStore](https://github.com/kubewharf/godel-scheduler/tree/main/pkg/util/generationstore) that provides a read/write (Get/Set) interface is abstracted and has two different implementations:

1.  ListStore: Doubly-linked List + HashMap[key]ListNodeItem

    Used in Cache, maintains time sequence through doubly-linked list, and quickly indexes to specific linked list elements through HashMap to implement $O(1)$ `addition` / `deletion` operations while maintaining time sequence.

    The data object we care about will be stored as a field of the linked list element, and the time sequence of the data object is updated when calling Set.

2.  RawStore: HashMap[key]Object

    Used in Snapshot, a pure data object storage.

We refactored all storage and reimplemented it as [GenerationStore](https://github.com/kubewharf/godel-scheduler/tree/main/pkg/util/generationstore). We can see that the E2E Latency has been reduced from minutes to **milliseconds** and has remained stable for a long time.

> PS: Note that the term E2E here refers to the time taken for a Pod within the entire scheduling cycle (from being dispatched by the Dispatcher to the completion of the final Binder binding).

## P11 Gödel Optimizations - Data Synchronization

![P11](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P11.png)

Next is another step of data synchronization.

For scheduling efficiency considerations, a Pod will NOT traverse all feasible nodes in the cluster when scheduling, but will stop immediately after traversing a specific number or a specific ratio, so the scheduling of each Pod has a certain spatial locality.

To achieve natural discreteness during scheduling, the scheduler Cache maintains a [NodeTree](https://github.com/kubernetes/kubernetes/blob/master/pkg/scheduler/internal/cache/node_tree.go) by topological zone. During data synchronization (UpdateSnapshot), the NodeTree is compressed into a one-dimensional list and stored in the snapshot, and accessed in a modular round-robin manner during each scheduling cycle.

However, this mechanism has obvious problems:

1. The generated one-dimensional list is not discrete, and only the front part can be evenly placed by zone, while the back part is often concentrated in a certain zone

2. The entire one-dimensional list will be frequently rebuilt (add, delete and other scenarios), which will bring huge computational overhead

Looking back at our needs, how can we achieve true discreteness?

=> It is equivalent to `any node having a random index in the NodeList`.

So how to avoid frequent reconstructions and instead reuse existing information to support randomness?

## P12 Gödel Optimizations - Data Synchronization

![P12](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P12.png)

Let's transform the existing linear list data structure. We aim for `insertion` and `deletion` of individual elements to be completed in $O(1)$ time complexity. Specifically:

- Insertion: Append directly to the end of the linear list.

- Deletion: Swap the element to be deleted with the last element in the list, then remove the last element (this requires a HashMap for fast indexing to support element swapping).

- Update: Perform a deletion followed by an insertion.

Interestingly, due to the randomness of Add/Delete/Update of all nodes in the entire cluster, the index of each node is also random. 

> PS: In any length interval, the ratio of nodes from different zones appearing is consistent with their total ratio.

## P13 Gödel Optimizations - Data Synchronization

![P13](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P13.png)

The final effect is that while achieving better discrete effects, the efficiency of NodeList maintenance is greatly improved.

As shown in the figure on the left, in a large-scale cluster with 20K+ Nodes, 1M+ Running Pods and a load of 1K Pods/s, the main distribution of E2E scheduling latency has shifted from minutes to milliseconds.

> Of course, a small part of the longer E2E distribution can still be seen in the upper right corner. This is mainly because the scheduling requirements of individual Pods cannot be met (for example, the cluster resources cannot meet the requirements). For Pods whose scheduling requirements can be met, the entire scheduling process can be completed in a shorter time.

## P14 Gödel Optimizations - Scheduling

![P14](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P14.png)

Let's talk about the scheduling phase, the issues we encountered, and the optimizations we've made. The first issue is **high water levels**.

Under the current `Filter` & `Score` mechanism, we need to find a specific number or proportion of feasible nodes in the `Filter` phase to proceed to the `Score` process (e.g., nodes node0,...,node3).

In scenarios with high cluster resource levels, meeting the `numOfFeasibleNodes` requirement often necessitates scanning a large number of nodes (e.g., the second row in the figure, node4,...,node12,...).

The upstream community has provided some configuration parameters ([scoring thresholds](https://kubernetes.io/docs/concepts/scheduling-eviction/scheduler-perf-tuning/)) to fine-tune the scheduler. However, static configurations are not suitable for large-scale production clusters with frequent resource fluctuations. 

We aim to develop a more **intelligent self-tuning mechanism** to address such issues and achieve the best balance between scheduling throughput and scheduling quality.

Specifically, the number of `feasible nodes to find` is no longer a fixed value but can adapt to the current cluster state and make adjustments accordingly.

A simple case: as the total number of filtered nodes increases, we can reduce the threshold for the number of feasible nodes to allow the filter process to complete earlier (e.g., as shown in the lower right corner of the figure).

> This is because when many nodes fail to pass the filter, it means the number of feasible solutions is likely very small.
> 
> In such cases, sacrificing a large amount of throughput to find the optimal solution within a very small set of feasible solutions is not worthwhile.
> 
> Especially since cluster conditions change rapidly, what is considered "optimal" is often a false notion, making early termination a reasonable choice.

In addition, we can also take more complex factors into account, such as the number of pending pods, the current incoming rate and throughput, etc.

Even in some scenarios that focus on scheduling quality (such as ML workloads), we can also change the decay mechanism to a growth mechanism.

Leaving aside the implementation details, the key point is that **all these adjustments will be done adaptively within the scheduler rather than by external intervention**.

## P15 Gödel Optimizations - Scheduling

![P15](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P15.png)

> Except for some Pods that are unschedulable at P99, the Algorithm Latency of most Pods is reduced by more than 50%.

## P16 Gödel Optimizations - Scheduling

![P16](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P16.png)

The second issue is the unschedulable scenario.

For unschedulable Pods, they may go through multiple rounds of scheduling during their entire life cycle, as shown in the figure

1.  The first round of scheduling failed, and all nodes were unavailable

2.  In the second round, there are quite a few nodes that have not changed, and there is no need to perform repeated calculations on these nodes

> PS: For simplicity, only the case without cross-nodes constraints is considered.

How to achieve this? We added **SchedulingContext** to Pod&Unit. The simplest example is to maintain the maximum node generation that was previously unschedulable in the Pod. If the generaion of a node encountered in the second round is not more than the value recorded in the previous round, it can be skipped directly.

> More fine-grained judgment and more intelligent queueing-hint mechanism in the future.

## P17 Gödel Optimizations - Scheduling

![P17](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P17.png)

We can look at the data and results. The indicator in the lower right corner is the percentage of nodes that have not changed between two rounds for unschedulable pods. We can see that many of them are above 70%.

On the left side, there's a trace of a non-schedulable Pod. The **SchedulingContext** mechanism reduced its filter processing time from 27ms to **7ms**.

> At the same time, it effectively reduces the interference and blocking of unschedulable tasks on other tasks.

## P18 Gödel Optimizations - Preemption

![P18](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P18.png)

Next, the preemption process.

Preemption is essentially a search tree, where computations are performed concurrently on multiple nodes to identify all potential victims at each node, as well as the actual victim to be selected. It also involves determining all node candidates.

The entire computation process is quite heavyweight. Assuming the process remains unchanged, how can we reduce the scale of the data involved in the computation?

## P19 Gödel Optimizations - Preemption

![P19](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P19.png)

1. How can we reduce the number of Pods participating in calculations on a specific node?

=> Considering that priority is the basic principle of preemption, we can classify and prioritize Pods on the node in advance (note that this should be dynamically maintained alongside Events).

For a specific incoming Pod, the set of Pods it can preempt is also fixed, which narrows down the data scale.

> PS: The GT/BE here refers to Gödel's QoS levels, which can be ignored.

## P20 Gödel Optimizations - Preemption

![P20](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P20.png)

2. How can we reduce the number of nodes involved in computations?

**[Top-left]** The essence of preemption is to free up resources. When priorities are clearly defined, the total amount of resources a Pod can free up through preemption is known.

> In fact, some Pods may not be preempted due to PDB restrictions.

**[Top-right]** However, if the resources released through preemption, combined with the node's available resources, are still insufficient for the current Pod's needs, preemption will inevitably fail. The problem then becomes whether we can quickly determine the maximum amount of resources that can be freed up through preemption for a specific priority value.

=> Essentially, this is about calculating the resource prefix sum based on priority order.

**[Bottom-left]** The challenge is that Pods are added and removed very frequently. How can we maintain the **order** while also managing the **resource prefix sum**? We introduced a Spary-Tree (a type of BST) to maintain interval properties through its subtree structure. By rotating the tree, we can convert prefix sums into interval sums. 

**[Bottom-right]** The Spary-Tree allows us to perform `insertions`, `deletions`, and `prefix sum queries` in $log(n)$ time complexity.

## P21 Gödel Optimizations - Preemption

![P21](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P21.png)

The final result is that we achieve highly efficient **heuristic pruning**. Not all nodes and pods will enter the calculation process.

> Under heuristic pruning, we can ensure that no feasible solutions are lost.

The preemption throughput of large-scale co-location clusters in tidal scenarios has been increased by **more than 10 times**, and cases that cannot be scheduled by preemption can be quickly filtered out within **2ms** (in the past, such cases were the most time-consuming).

## P22 Gödel Optimizations - Unit Semantic & Unit Framework

![P22](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P22.png)

In addition, Gödel has some innovative designs that help achieve performance optimization while providing better scalability.

The first is **Unit Semantic and Unit Framework**.

The specific details here will not be expanded. We only need to know that compared with `Pod Framework`, `Unit Framwork` focuses on the `scheduling stage division` and `scheduling data preprocessing` at the Unit level.

For example, for DaemonSet Pod, the Nodes is preprocessed in the Locating stage, and its scope is narrowed to one node before entering the subsequent scheduling and preemption process. In large-scale clusters, the scheduling latency of DS Pods has dropped from 30ms to **0.3ms**.

In addition, under the Unit Framework, it is easier to reuse calculation results through **Unit aggregation**, further improving scheduling efficiency.

## P23 Gödel Optimizations - Unit Semantic & Unit Framework

![P23](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P23.png)

The ApplicationUnit Distribution shows that we have effectively aggregated thousands of Pods and scheduled them as a unit.

In a ultra-large-scale cluster with nearly 25K+ nodes, we have suppressed the fluctuation of SLO within **1 second**.

> It can be seen that the overall SLO curve has been very stable since the upgrade on 2024-04-09.

## P24 Gödel Optimizations - CommonStore Data Flow

![P24](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P24.png)

The last one is the **[CommonStore](https://github.com/kubewharf/godel-scheduler/blob/main/pkg/common/store/basestore.go) Data Flow mechanism**.

Our idea is different from upstream Kubernetes Scheduler. We will try our best to avoid centralized temporary calculations in the serial scheduling process. Instead, we prefer to maintain some information in real time based on events to reduce the computing burden of the plug-in runtime.

Specifically, we strictly divide the data source of Cache into two categories:

1. Respond to "exogenous" events to maintain the status of the cluster (such as Add/Update/Delete of ResourceObject)

2. Respond to "endogenous" scheduling decisions and maintain some temporary data (such as AssumePod/ForgetPod)

On this basis, we will perform various data preprocessing in the event handling process of Cache, and expose the data access interface to the plug-in from Snapshot in the form of StoreHandle to accelerate the plug-in calculation.

The specific layered design and data link are complex, so we will not expand them here. The important thing is that through this mechanism, we can effectively **avoid the generation of new computing hotspots while continuously developing new features**.

> A typical example of open source code is [PDB Store](https://github.com/kubewharf/godel-scheduler/blob/main/pkg/scheduler/cache/commonstores/pdb_store/pdb_store.go), which avoids the computational loss of List PDB and temporary Match by maintaining relevant matching relationships in advance.

## P25 Gödel Optimizations - Achievements

![P25](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P25.png)

## P26 Gödel Scheduling System - Future Work

![P26](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P26.png)

-   Optimization of inter-component communication mechanisms

    *Currently, the communication of the entire system is based on a centralized API Server. After the multi-shard throughput reaches 5K+. Pods/s, it is difficult to continue to increase. We will solve this problem by splitting the communication link*

-   More general batch scheduling

-   More rational separation of plugin and storage implementation

    *More reasonable mapping logic between plugins and storage, and continuous optimization of plugin calculation process*

-   Intelligent queueing

    *Reduce invalid scheduling attempts and ensure better workload fairness*

-   ...

## P27 THANK YOU

![P27](https://raw.githubusercontent.com/binacs/blog/main/img/kubecon_2024_cn/P27.png)

https://github.com/kubewharf/godel-scheduler/