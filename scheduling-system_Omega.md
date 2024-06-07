# Omega

## 1. Introduction

![omega-arch](https://raw.githubusercontent.com/binacs/blog/main/img/omega-arch.svg)

We identified the two prevalent scheduler architectures shown in Figure 1. *Monolithic schedulers* use a single, centralized scheduling algorithm for all jobs (our existing scheduler is one of these). *Two-level* schedulers have a single active resource manager that offers compute resources to multiple parallel, independent “scheduler frameworks”, as in Mesos [13] and Hadoop-on-Demand [4].

Neither of these models satisfied our needs. Monolithic schedulers do not make it easy to add new policies and specialized implementations, and may not scale up to the cluster sizes we are planning for. Two-level scheduling architectures do appear to provide flexibility and parallelism, but in practice their conservative resource-visibility and locking algorithms limit both, and make it hard to place difficult-to-schedule “picky” jobs or to make decisions that require access to the state of the entire cluster.

Our solution is a new parallel scheduler architecture built around *shared state*, using lock-free optimistic concurrency control, to achieve both implementation extensibility and performance scalability. This architecture is being used in *Omega*, Google’s next-generation cluster management system.

## 2. Requirements

### 2.1 Workload heterogeneity

There are many ways of partitioning a cluster’s workload between different schedulers. Here, we pick a simple two-way split between long-running *service* jobs that provide end-user operations (e.g., web services) and internal infrastructure services (e.g., BigTable [5]), and *batch* jobs which perform a computation and then finish. Although many other splits are possible, for simplicity we put all low priority jobs1 and those marked as “best effort” or “batch” into the batch category, and the rest into the service category.

A job is made up of one or more tasks – sometimes thousands of tasks. Most (>80%) jobs are batch jobs, but the majority of resources (55–80%) are allocated to service jobs (Figure 2); the latter typically run for much longer (Figure 3), and have fewer tasks than batch jobs (Figure 4).

>   Why does this matter?
>
>   -   Many batch jobs are short, and fast turnaround is important, so a lightweight, low-quality approach to placement works just fine. 
>   -   But long-running, high-priority service jobs (20–40% of them run for over a month) must meet stringent availability and performance targets, meaning that careful placement of their tasks is needed to maximize resistance to failures and provide good performance.

Indeed, the Omega service scheduler will try to place tasks to resist both independent and coordinated failures, which is an NP-hard chance-constrained optimization problem with tens of failure domains that nest and overlap. Our previous implementation could take tens of seconds to do this. While it is very reasonable to spend a few seconds making a decision whose effects last for several weeks, it can be problematic if an interactive batch job has to wait for such a calculation. This problem is typically referred to as “head of line blocking”, and can be avoided by introducing parallelism.

## 3. Taxonomy

Design issues:

-   Partitioning the scheduling work
-   Choice of resources
-   Interference
-   Allocation granularity
-   Cluster-wide behaviors

### 3.1 Monolithic schedulers

-   A monolithic scheduler usually runs a single instance of the scheduling code, and applies the same algorithm for all incoming jobs.

    >   eg: HPC schedulers such as Maui [16] and its successor Moab, as well as Platform LSF [14]

-   Provide multiple code paths in the scheduler, running separate scheduling logic for different job types.

### 3.2 Statically partitioned schedulers

This leads to fragmentation and suboptimal utilization, which is not viable for us.

### 3.3 Two-level scheduling

An obvious fix to the issues of static partitioning is to adjust the allocation of resources to each scheduler dynamically, using a central coordinator to decide how many resources each sub-cluster can have. This *two-level scheduling* approach is used by a number of systems, including Mesos [13] and Hadoop-on-Demand (HOD) [4].

>   Concurrency control is pessimistic.

Mesos works best when tasks are short-lived and relinquish resources frequently, and when job sizes are small compared to the size of the cluster.

>   YARN is effectively a monolithic scheduler architecture.

### 3.4 Shared-state scheduling

The alternative used by Omega is the *shared state* approach: we grant each scheduler full access to the entire cluster, allow them to compete in a free-for-all manner, and use optimistic concurrency control to mediate clashes when they update the cluster state. This immediately eliminates two of the issues of the two-level scheduler approach – limited parallelism due to pessimistic concurrency control, and restricted visibility of resources in a scheduler framework – at the potential cost of redoing work when the optimistic concurrency assumptions are incorrect.

There is no central resource allocator in Omega; all of the resource-allocation decisions take place in the schedulers. We maintain a resilient master copy of the resource allocations in the cluster, which we call *cell state*.4 Each scheduler is given a private, local, frequently-updated copy of cell state that it uses for making scheduling decisions. The scheduler can see the entire state of the cell and has complete freedom to lay claim to any available cluster resources provided it has the appropriate permissions and priority – even ones that another scheduler has already acquired. Once a scheduler makes a placement decision, it updates the shared copy of cell state in an atomic commit. At most one such commit will succeed in the case of conflict: effectively, the time from state synchronization to the commit attempt is a *transaction*. Whether or not the transaction succeeds, the scheduler resyncs its local copy of cell state afterwards and, if necessary, re-runs its scheduling algorithm and tries again.

Omega schedulers operate completely in parallel and do not have to wait for jobs in other schedulers, and there is no inter-scheduler head of line blocking. To prevent conflicts from causing starvation, Omega schedulers typically choose to use incremental transactions, which accept all but the conflicting changes (i.e., the transaction provides atomicity but not independence). A scheduler can instead use an all-or-nothing transaction to achieve gang scheduling: either all tasks of a job are scheduled together, or none are, and the scheduler must try to schedule the entire job again. This helps to avoid resource hoarding, since a gang-scheduled job can preempt lower-priority tasks once sufficient resources are available and its transaction commits, and allow other schedulers’ jobs to use the resources in the meantime.

Different Omega schedulers can implement different policies, but all must agree on what resource allocations are permitted (e.g., a common notion of whether a machine is full), and a common scale for expressing the relative importance of jobs, called *precedence*. These rules are deliberately kept to a minimum. The two-level scheme’s centralized resource allocator component is thus simplified to a persistent data store with validation code that enforces these common rules. Since there is no central policy-enforcement engine for high-level cluster-wide goals, we rely on these showing up as emergent behaviors that result from the decisions of individual schedulers. In this, it helps that fairness is not a primary concern in our environment: we are driven more by the need to meet business requirements. In support of these, individual schedulers have configuration settings to limit the total amount of resources they may claim, and to limit the number of jobs they admit. Finally, we also rely on *postfacto* enforcement, since we are monitoring the system’s behavior anyway.

## 4. Design comparisons

-   A lightweight simulator driven by synthetic workloads using parameters drawn from empirical workload distributions.
-   A high-fidelity simulator that replays historic workload traces from Google production clusters, and reuses much of the Google production scheduler’s code.

### 4.1 Monolithic schedulers

The results are not surprising: in the single-path baseline case, the scheduler busyness is low as long as scheduling is quick, but scales linearly with increased $$t_{job}$$ (Figure 6a). As a consequence, job wait time increases at a similar rate until the scheduler is saturated, at which point it cannot keep up with the incoming workload any more. The wait time curves for service jobs closely track the ones for batch jobs, since all jobs take the same time to schedule (Figure 5a).

With a fast path for batch jobs in the multi-path case, both average job wait time and scheduler busyness decrease significantly even at long decision times for service jobs, since the majority of jobs are batch ones. But batch jobs can still get stuck in a queue behind the slow-to-schedule service jobs, and head-of-line blocking occurs: scalability is still limited by the processing capacity of a single scheduler (Figures 5b and 6b). To avoid this, we need some form of parallel processing.

### 4.2 Two-level scheduling: Mesos

We simulate a single resource manager and two scheduler frameworks, one handling batch jobs and one handling service jobs. To keep things simple, we assume that a scheduler only looks at the set of resources available to it when it begins a scheduling attempt for a job (i.e., any offers that arrive during the attempt are ignored). Resources not used at the end of scheduling a job are returned to the allocator; they may be re-offered again if the framework is the one furthest below its fair share. The DRF algorithm used by Mesos’s centralized resource allocator is quite fast, so we assume it takes 1 ms to make a resource offer.

The batch scheduler busyness (Figure 7b) turns out to be much higher than in the monolithic multi-path case. This is a consequence of an interaction between the Mesos offer model and the service scheduler’s long scheduling decision times. Mesos achieves fairness by alternately offering *all* available cluster resources to different schedulers, predicated on assumptions that resources become available frequently and scheduler decisions are quick. As a result, a long scheduler decision time means that nearly all cluster resources are locked down for a long time, inaccessible to other schedulers. The only resources available for other schedulers in this situation are the few becoming available while the slow scheduler is busy. These are often insufficient to schedule an above-average size batch job, meaning that the batch scheduler cannot make progress while the service scheduler holds an offer. It nonetheless keeps trying, and as a consequence, we find that a number of jobs are abandoned because they did not finish scheduling their tasks by the 1,000-attempt retry limit in the Mesos case (Figure 7c).

### 4.3 Shared-state scheduling: Omega

We again simulate two schedulers: one handling the batch workload, one handling the service workload. Both schedulers refresh their local copy of cell state by synchronizing it with the shared one when they start looking at a job, and work on their local copy for the duration of the decision time. Assuming at least one task got scheduled, a transaction to update the shared cell state is issued once finished. If there are no conflicts, then the entire transaction is accepted; otherwise only those changes that do not result in an overcommitted machine are accepted.

Since the batch scheduler is the main scalability bottleneck, we repeat the same scaling experiment with multiple batch schedulers in order to test the ability of the Omega model to scale to larger loads. The batch scheduling work is load-balanced across the schedulers using a simple hashing function. As expected, the conflict fraction increases with more schedulers as more opportunities for conflict exist (Figure 9a), but this is compensated – at least up to 32 batch schedulers – by the better per-scheduler busyness with more schedulers (Figure 9b). Similar results are seen with the job wait times (not shown here). This is an encouraging result: the Omega model can scale to a high batch workload while still providing good behavior for service jobs.

### 4.4 Summary

In short, the monolithic scheduler is not scalable. Although adding the multi-path feature reduces the average scheduling decision time, head-of-line blocking is still a problem for batch jobs, and means that this model may not be able to scale to the workloads we project for large clusters. The two-level model of Mesos can support independent scheduler implementations, but it is hampered by pessimistic locking, does not handle long decision times well, and could not schedule much of the heterogeneous load we offered it.

The shared-state Omega approach seems to offer competitive, scalable performance with little interference at realistic operating points, supports independent scheduler implementations, and exposes the entire allocation state to the schedulers.

## 5. Trace-driven simulation

### 5.1 Scheduling performance

-   Scaling the workload.
-   Load-balancing the batch scheduler.

### 5.2 Dealing with conflicts

Clearly, incremental transactions should be the default.

## 6. Flexibility: a MapReduce scheduler

What if the number of workers could be chosen automatically if additional resources were available, so that jobs could complete sooner? Our specialized MapReduce scheduler does just this by opportunistically using idle cluster resources to speed up MapReduce jobs. It observes the overall resource utilization in the cluster, predicts the benefits of scaling up current and pending MapReduce jobs, and apportions some fraction of the unused resources across those jobs according to some policy.

### 6.1 Implementation

We consider three different policies for adding resources: *max-parallelism*, which keeps on adding workers as long as benefit is obtained, *global cap*, which stops the MapReduce scheduler using idle resources if the total cluster utilization is above a target value, and *relative job size*, which limits the maximum number of workers to four times as many as it initially requested. In each case, a set of resource allocations to be investigated is run through the predictive model, and the allocation leading to the earliest possible finish time is used. More elaborate approaches and objective functions, such as used in deadline-based schedulering [10], are certainly possible, but not the focus of this case study.

### 6.2 Evaluation

...

## 7. Additional related work

...

## 8. Conclusions and future work

Future work could usefully focus on ways to provide global guarantees (fairness, starvation avoidance, etc.) in the Omega model: this is an area where centralized control makes life easier.