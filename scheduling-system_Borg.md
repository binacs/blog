# Borg

## 1 Introduction

![borg-arch](https://raw.githubusercontent.com/BinacsLee/blog/main/img/borg-arch.svg)



## 2 The user perspective

### 2.1 The workload

| Borg Jobs                                 | Long-running | CPU Allocated / Usage | Mem Allocated / Usage |
| ----------------------------------------- | ------------ | --------------------- | --------------------- |
| production *(higher-priority)*            | 1            | 70% / 60%             | 55% / 85%             |
| non-production *(most of the batch jobs)* | 0            |                       |                       |

### 2.2 Clusters and cells

-   10K cluster nodes

### 2.3 Jobs and tasks

-   have constrains
-   run as containers

-   template

The following figure illustrates the states that jobs and tasks go through during their lifetime.

![borg-state-machine](https://raw.githubusercontent.com/BinacsLee/blog/main/img/borg-state-machine.svg)



>   Users can trigger `submit`, `kill` and `update` transitions.

Users can change the properties of some or all of the tasks in a running job by pushing a new job configuration to Borg, and then instructing Borg to `update` the tasks to the new specification.

>   eg: Kubernetes API spec

Updates are generally done in a rolling fashion, and a limit can be imposed on the number of task disruptions (reschedules or preemptions) an update causes; any changes that would cause more disruptions are skipped.

>   eg: Kubernetes PDB

Some task updates (e.g., pushing a new binary) will always require the task to be restarted; some (e.g., increasing resource requirements or changing constraints) might make the task no longer fit on the machine, and cause it to be stopped and rescheduled; and some (e.g., changing priority) can always be done without restarting or moving the task.

>   eg: Kubernetes will create a new Pod anyway
>
>   Daemon jobs should be upgraded in place as much as possible

Tasks can ask to be notified via a Unix SIGTERM signal before they are preempted by a SIGKILL, so they have time to clean up, save state, finish any currently-executing requests, and decline new ones.

>   eg: Terminating grace

### 2.4 Allocs

A Borg *alloc* (short for allocation) is a reserved set of resources on a machine in which one or more tasks can be run; the resources remain assigned whether or not they are used. 

An *alloc set* is like a job: it is a group of allocs that reserve resources on multiple machines. Once an alloc set has been created, one or more jobs can be submitted to run in it. For brevity, we will generally use “task” to refer to an alloc or a top-level task (one outside an alloc) and “job” to refer to a job or alloc set.

### 2.5 Priority, quota, and admission control

Borg defines non-overlapping *priority bands* for different uses, including (in decreasing-priority order): monitoring, production, batch, and best effort (also known as testing or free).

>   `prod` jobs belong are the ones in the monitoring and production bands

Although a preempted task will often be rescheduled elsewhere in the cell, preemption cascades could occur if a high-priority task bumped out a slightly lower-priority one, which bumped out another slightly-lower priority task, and so on. To eliminate most of this, we disallow tasks in the production priority band to preempt one another.

>   Pay attention to the definition of priority and the use of priority

*Quota* is used to decide which jobs to *admit* for scheduling. Quota is expressed as a vector of resource quantities (CPU, RAM, disk, etc.) at a given priority, for a period of time (typically months). The quantities specify the maximum amount of resources that a user’s job requests can ask for at a time.

The use of quota reduces the need for policies like Dominant Resource Fairness (DRF).

### 2.6 Naming and monitoring

Borg creates a stable “Borg name service” (BNS) name for each task that includes the cell name, job name, and task number.

>   eg: the fiftieth task in job jfoo owned by user ubar in cell cc would be reachable via 50.jfoo.ubar.cc.borg.google.com.

Almost every task run under Borg contains a built-in HTTP server that publishes information about the health of the task and thousands of performance metrics (e.g., RPC latencies). Borg monitors the health-check URL and restarts tasks that do not respond promptly or return an HTTP error code.

>   eg: Health Check

## 3 Borg architecture

>   Written in C++

### 3.1 Borgmaster

Each cell’s Borgmaster consists of two processes: the main Borgmaster process and a separate scheduler.

The main Borgmaster process handles client RPCs that either mutate state (e.g., create job) or provide read-only access to data (e.g., lookup job). It also manages state machines for all of the objects in the system (machines, tasks, allocs, etc.), communicates with the Borglets, and offers a web UI as a backup to Sigma.

>   Five replicas and Paxos
>
>   Electing a master and failing-over to the new one typically takes about 10 s, but can take up to a minute in a big cell because some in-memory state has to be reconstructed. When a replica recovers from an outage, it dynamically re-synchronizes its state from other Paxos replicas that are up-to-date.

The Borgmaster’s state at a point in time is called a *checkpoint*, and takes the form of a periodic snapshot plus a change log kept in the Paxos store.

A high-fidelity Borgmaster simulator called Fauxmaster can be used to read checkpoint files, and contains a complete copy of the production Borgmaster code, with stubbed-out interfaces to the Borglets.

>   eg: Kubernetes simulator

### 3.2 Scheduling

When a job is submitted, the Borgmaster records it persistently in the Paxos store and adds the job’s tasks to the *pending* queue. This is scanned asynchronously by the *scheduler*, which assigns tasks to machines if there are sufficient available resources that meet the job’s constraints. (The scheduler primarily operates on tasks, not jobs.) The scan proceeds from high to low priority, modulated by a round-robin scheme within a priority to ensure fairness across users and avoid head-of-line blocking behind a large job. The scheduling algorithm has two parts: *feasibility checking*, to find machines on which the task could run, and *scoring*, which picks one of the feasible machines.

>   eg: Filter and Score

Borg originally used a variant of E-PVM [4] for scoring, which generates a single cost value across heterogeneous resources and minimizes the change in cost when placing a task.The opposite end of the spectrum is “best fit”, which tries to fill machines as tightly as possible.

>   eg: Most-Allocated and Least-Allocated

If the machine selected by the scoring phase doesn’t have enough available resources to fit the new task, Borg *preempts* (kills) lower-priority tasks, from lowest to highest priority, until it does. We add the preempted tasks to the scheduler’s pending queue, rather than migrate or hibernate them.

To reduce task startup time, the scheduler prefers to assign tasks to machines that already have the necessary packages (programs and data) installed: most packages are immutable and so can be shared and cached. (This is the only form of data locality supported by the Borg scheduler.) In addition, Borg distributes packages to machines in parallel using tree and torrent-like protocols.

>   eg: Affinity and Anti-Affinity
>
>   Shared package downloading

### 3.3 Borglet

The Borglet is a local Borg agent that is present on every machine in a cell. It starts and stops tasks; restarts them if they fail; manages local resources by manipulating OS kernel settings; rolls over debug logs; and reports the state of the machine to the Borgmaster and other monitoring systems.

If a Borglet does not respond to several poll messages its machine is marked as down and any tasks it was running are rescheduled on other machines. If communication is restored the Borgmaster tells the Borglet to kill those tasks that have been rescheduled, to avoid duplicates.

>   eg: Re-create a Pod

### 3.4 Scalability

Early versions of Borgmaster had a simple, synchronous loop that accepted requests, scheduled tasks, and communicated with Borglets. To handle larger cells, we split the scheduler into a separate process so it could operate in parallel with the other Borgmaster functions that are replicated for failure tolerance. A scheduler replica operates on a cached copy of the cell state. It repeatedly: retrieves state changes from the elected master (including both assigned and pending work); updates its local copy; does a scheduling pass to assign tasks; and informs the elected master of those assignments. The master will accept and apply these assignments unless they are inappropriate (e.g., based on out of date state), which will cause them to be reconsidered in the scheduler’s next pass.

To improve response times, we added separate threads to talk to the Borglets and respond to read-only RPCs. For greater performance, we sharded (partitioned) these functions across the five Borgmaster replicas.

Several things make the Borg scheduler more scalable:

-   **Score caching**: Evaluating feasibility and scoring a machine is expensive, so Borg caches the scores until the properties of the machine or task change – e.g., a task on the machine terminates, an attribute is altered, or a task’s requirements change. Ignoring small changes in resource quantities reduces cache invalidations.

    >   eg: Cache scheduling results based on pod owner reference

-   **Equivalence classes**: Tasks in a Borg job usually have identical requirements and constraints, so rather than determining feasibility for every pending task on every machine, and scoring all the feasible machines, Borg only does feasibility and scoring for one task per *equivalence class* – a group of tasks with identical requirements.

    >   eg: Schedule based on Pod template

-   **Relaxed randomization**: It is wasteful to calculate feasibility and scores for all the machines in a large cell, so the scheduler examines machines in a random order until it has found “enough” feasible machines to score, and then selects the best within that set. This reduces the amount of scoring and cache invalidations needed when tasks enter and leave the system, and speeds up assignment of tasks to machines. Relaxed randomization is somewhat akin to the batch sampling of Sparrow [65] while also handling priorities, preemptions, heterogeneity and the costs of package installation.

    >   eg: Randomization is used in scheduling, but traversal is used in preemption

## 4 Avaliability

-   automatically reschedules evicted tasks, on a new machine if necessary;
-   reduces correlated failures by spreading tasks of a job across failure domains such as machines, racks, and power domains;
-   limits the allowed rate of task disruptions and the number of tasks from a job that can be simultaneously down during maintenance activities such as OS or machine upgrades;

-   uses declarative desired-state representations and idempotent mutating operations, so that a failed client can harmlessly resubmit any forgotten requests;
-   rate-limits finding new places for tasks from machines that become unreachable, because it cannot distinguish between large-scale machine failure and a network partition;
-   avoids repeating task::machine pairings that cause task or machine crashes; and
-   recovers critical intermediate data written to local disk by repeatedly re-running a logsaver task (§2.4), even if the alloc it was attached to is terminated or moved to another machine. Users can set how long the system keeps trying; a few days is common.

## 5 Utilization

...

## 6 Isolation

### 6.1 Security isolation

borgssh

### 6.2 Performance isolation

Linux cgroup-based resource container

To help with overload and overcommitment:

-   Borg tasks have an application class or *appclass*. The most important distinction is between the *latency-sensitive* (LS) appclasses and the rest, which we call *batch* in this paper. LS tasks are used for user-facing applications and shared infrastructure services that require fast response to requests. High-priority LS tasks receive the best treatment, and are capable of temporarily starving batch tasks for several seconds at a time.

    >   eg: Online applications

-   A second split is between *compressible* resources (e.g., CPU cycles, disk I/O bandwidth) that are rate-based and can be reclaimed from a task by decreasing its quality of service without killing it; and *non-compressible* resources (e.g., memory, disk space) which generally cannot be reclaimed without killing the task. If a machine runs out of non-compressible resources, the Borglet immediately terminates tasks, from lowest to highest priority, until the remaining reservations can be met. If the machine runs out of compressible resources, the Borglet throttles usage (favoring LS tasks) so that short load spikes can be handled without killing any tasks. If things do not improve, Borgmaster will remove one or more tasks from the machine.

    >   eg: QoS

-   A user-space control loop in the Borglet assigns memory to containers based on predicted future usage (for prod tasks) or on memory pressure (for non-prod ones); handles Out-of-Memory (OOM) events from the kernel; and kills tasks when they try to allocate beyond their memory limits, or when an over-committed machine actually runs out of memory. Linux’s eager file-caching significantly complicates the implementation because of the need for accurate memory-accounting.

    >   eg: Socket binding

## 7 Related work

-   Apache Mesos
-   YARN (Hadoop-centric)

-   Tupperware
-   Aurora
-   Autopilot
-   Quincy (network flow model)
-   Cosmos (batch)
-   Apolo
-   Fuxi
-   Omega
-   Kubernetes

## 8 Lessons and future work

### 8.1 Lessons learned: the bad

**Jobs are restrictive as the only grouping mechanism for tasks.**

Kubernetes rejects the job notion and instead organizes its scheduling units (pods) using *labels* – arbitrary key/value pairs that users can attach to any object in the system. The equivalent of a Borg job can be achieved by attaching a job:jobname label to a set of pods, but any other useful grouping can be represented too, such as the service, tier, or release-type (e.g., production, staging, test). Operations in Kubernetes identify their targets by means of a label query that selects the objects that the operation should apply to. This approach gives more flexibility than the single fixed grouping of a job.

**One IP address per machine complicates things.**

Kubernetes can take a more user-friendly approach that eliminates these complications: every pod and service gets its own IP address, allowing developers to choose ports rather than requiring their software to adapt to the ones chosen by the infrastructure, and removes the infrastructure complexity of managing ports.

**Optimizing for power users at the expense of casual ones.**

### 8.2 Lessons learned: the good

**Allocs are useful.**

Kubernetes equivalent of an alloc is the *pod*, which is a resource envelope for one or more containers that are always scheduled onto the same machine and can share resources. Kubernetes uses helper containers in the same pod instead of tasks in an alloc, but the idea is the same.

**Cluster management is more than task management.**

Kubernetes supports naming and load balancing using the *service* abstraction.

**Introspection is vital.**

Kubernetes aims to replicate many of Borg’s introspection techniques. For example, it ships with tools such as cAdvisor [15] for resource monitoring, and log aggregation based on Elasticsearch/Kibana [30] and Fluentd [32]. The master can be queried for a snapshot of its objects’ state. Kubernetes has a unified mechanism that all components can use to record events (e.g., a pod being scheduled, a container failing) that are made available to clients.

**The master is the kernel of a distributed system.**

The Kubernetes architecture goes further: it has an API server at its core that is responsible only for processing requests and manipulating the underlying state objects. The cluster management logic is built as small, composable micro-services that are clients of this API server, such as the replication controller, which maintains the desired number of replicas of a pod in the face of failures, and the node controller, which manages the machine lifecycle.
