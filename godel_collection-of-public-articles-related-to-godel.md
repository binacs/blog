# Collection of Public Articles Related to Gödel

## Gödel System

-   [2024] [ByteDance open-sources Gödel Scheduler: a unified scheduler for online and offline tasks / 字节跳动开源 Gödel Scheduler：在离线统一调度器](https://mp.weixin.qq.com/s/771IUzZTC-fqBahC6RoeRA)

-   [2024] [Gödel Scheduler performance optimization: algorithm design ideas and data structure application / Gödel Scheduler 性能优化: 算法设计思想与数据结构应用](https://mp.weixin.qq.com/s/xEYR_vC9LDaka9-EwalqcA)

-   [2024] [Interpretation of the SoCC paper: How ByteDance performs unified resource scheduling in large-scale clusters / SoCC 论文解读：字节跳动如何在大规模集群中进行统一资源调度](https://mp.weixin.qq.com/s/1nLD3QykR1eLuV9umyOCYg)

> **About Colocation**
>
> The left figure below describes the resource allocation of online and offline tasks in a cluster over a period of time. In the initial stage, online tasks do not consume many resources, and a large amount of computing resources are allocated to offline tasks with lower priority. When the resource demand of online tasks surges due to a special event (emergency, hot search, etc.), Gödel immediately allocates resources to online tasks, and the resource allocation of offline tasks decreases rapidly. After the peak, online tasks begin to reduce resource requests, and the scheduler shifts resources to offline tasks again. By combining offline pools and dynamic resource transfer, ByteDance can always maintain a high resource utilization rate. During the evening peak hours, the average resource rate of the cluster reaches more than 60%, and it can also be maintained at around 40% during the daytime trough stage.
>
> ![colocation](https://raw.githubusercontent.com/binacs/blog/main/img/godel/colocation.webp)



---

## ML on Gödel

-   [2022] [Xin Tao: ByteDance's cloud-native machine learning system implementation / 辛涛：字节跳动机器学习系统云原生落地实践](https://mp.weixin.qq.com/s/D1qcC-bjlo2m3OwQ70lmRA)

-   [2022] [From 1 million cores to 4.5 million cores: ByteDance's ultra-large-scale cloud-native offline training practice / 从100w核到450w核：字节跳动超大规模云原生离线训练实践](https://mp.weixin.qq.com/s/uGBy-WpdjTMUy-7MQAZiww)



## BigData on Gödel

-   [2022] [ByteDance YARN Cloud Native Evolution Practice / 字节跳动 YARN 云原生化演进实践](https://mp.weixin.qq.com/s/a6P1ZrIoy6xlHrTG2-GNKQ)

-   [2023] [ByteDance Spark supports tens of thousands GPUs model inference practice / 字节跳动 Spark 支持万卡模型推理实践](https://mp.weixin.qq.com/s/57c9AlA34b-ofLmA8eZdxg)

-   [2023] [ByteDance Spark Shuffle large-scale cloud-native evolution practice / 字节跳动 Spark Shuffle 大规模云原生化演进实践](https://mp.weixin.qq.com/s/ohubEgwFpyzVYboY-0dX5A)

-   [2023] [ByteDance Flink's large-scale cloud-native practice / 字节跳动 Flink 大规模云原生化实践](https://mp.weixin.qq.com/s/a0w4NMcpetigk58YhANS6Q)



---

## High-level Evolution

-   [2022] [ByteDance’s evolution of cloud-native technology / 字节跳动的云原生技术历程演进](https://mp.weixin.qq.com/s/YM77RAZhkLiqZ3rqg3uXHA)

-   [2023] [ByteDance's multi-cloud and cloud-native practice / 字节跳动的多云云原生实践之路](https://mp.weixin.qq.com/s/rBys9jxNyArpZ_d2ah1E1A)
-   [2022] [From hybrid deployment to unified scheduling: ByteDance's container scheduling technology evolution / 从混合部署到融合调度：字节跳动容器调度技术演进之路](https://mp.weixin.qq.com/s/AKt-RQjFwDRD7tGBnrqkSQ)
-   [2022] [ByteDance's large-scale K8s cluster management practice / 字节跳动大规模 K8s 集群管理实践](https://mp.weixin.qq.com/s/suVOO9cdWsoHW6_foGbbhw)



##  Related Components

-   [KubeWharf: A practice-driven cloud native project set / KubeWharf: 一个实践驱动的云原生项目集](https://mp.weixin.qq.com/s/C2LP0Owqo1jSBKeNAVqsvw)

-   [ByteDance Open Sources Katalyst: Online-Offline Colocation Scheduling, Upgrade Cost Optimization / 字节跳动开源 Katalyst：在离线混部调度，成本优化升级](https://mp.weixin.qq.com/s/A5_1h3RLmDNazmAddbhYaA)

-   [Katalyst: ByteDance's cloud-native cost optimization practice / Katalyst：字节跳动云原生成本优化实践](https://mp.weixin.qq.com/s/d4R2mIzkd-7FIcNKK5S6LQ)

-   [ByteDance open-sources KubeAdmiral: a new generation of multi-cluster orchestration and scheduling engine based on Kubernetes / 字节跳动开源 KubeAdmiral：基于 Kubernetes 的新一代多集群编排调度引擎](https://mp.weixin.qq.com/s/aS18urPF8UB4K2I_9ECbHg)

-   [KubeGateway: ByteDance kube-apiserver high availability solution / KubeGateway: 字节跳动 kube-apiserver 高可用方案](https://mp.weixin.qq.com/s/sDxkXPmgtCknwtnwvg2EMw)

-   [KubeBrain: Exploration and practice of ByteDance's high-performance Kubernetes metadata storage solution / KubeBrain: 字节跳动高性能 Kubernetes 元信息存储方案探索与实践 ](https://mp.weixin.qq.com/s/lxukeguHP1l0BGKbAa89_Q)

-   [KubeZoo: ByteDance's lightweight multi-tenant open source solution / KubeZoo：字节跳动轻量级多租户开源解决方案](https://mp.weixin.qq.com/s/SUNuvFz4HBmFk-XDN0mINg)

-   [ByteDance open-sources Kelemetry: a global tracing system for the Kubernetes control plane / 字节跳动开源 Kelemetry：面向 Kubernetes 控制面的全局追踪系统](https://mp.weixin.qq.com/s/U-P9tZhX4rT5wTaSnqfoZg)



## Hybrid Deployment (Colocation)

-   [2023] [The secret to reducing costs and increasing efficiency: How Douyin Group implements tidal co-location / 降本增效的秘密：抖音集团如何实践潮汐混部](https://mp.weixin.qq.com/s/dRqge-_BnbK1WsmXo6OuBw)

-   [2022] [ByteDance implements topology-aware online and offline pooling based on large-scale elastic scaling / 字节跳动基于大规模弹性伸缩实现拓扑感知的在离线并池](https://mp.weixin.qq.com/s/CQJmH_er9pmh8Bm9Joh_Vg)

