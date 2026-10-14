# Third-party notices / 第三方来源与许可

The root [Apache-2.0 license](LICENSE) covers original Joker + JEV material. It does not relicense dependencies, downloaded weights, fonts, browser binaries or remote services. The project does not bundle pretrained checkpoints. Preserve applicable upstream license and attribution files when redistributing third-party material.

根目录 Apache-2.0 适用于本项目原创内容，不改变第三方依赖、下载权重、字体、浏览器二进制或托管服务的授权。仓库不分发预训练权重；再次分发第三方内容时，应随附其适用的许可证和署名文件。

## Strategy model / 策略模型

- **DouZero 1.1.0** — Apache-2.0. The project imports its model architectures and observation encoders for inference; it does not train new weights. [Source and license](https://github.com/kwai/DouZero) · [PyPI release](https://pypi.org/project/douzero/1.1.0/).
- **DouZero ADP checkpoints distributed with PerfectDou** — downloaded from the PerfectDou repository at commit `594404922ee3810e2d84b80bb2c2846cb20e5390`. That repository carries [Apache-2.0](https://github.com/Netease-Games-AI-Lab-Guangzhou/PerfectDou/blob/594404922ee3810e2d84b80bb2c2846cb20e5390/LICENSE) and identifies these files as the **DouZero ADP baseline**, distinct from its PerfectDou model. [Release context](https://github.com/Netease-Games-AI-Lab-Guangzhou/PerfectDou/blob/594404922ee3810e2d84b80bb2c2846cb20e5390/README.md) · [Pinned download URLs, sizes and SHA-256 hashes](games/doudizhu/models/manifest.json).

实际策略是 DouZero ADP；从 PerfectDou 仓库下载基线权重不代表本项目运行 PerfectDou。下载器固定来源与哈希，权重保存在 Git 忽略目录。上游仓库的许可证与权重来源在此分别列明，不将本项目版权声明套用到它们。

## Optional vision backend / 可选视觉后端

- **Perplexity `pplx-decider-v1.1-27b`** — its [model card at revision `14c9d90137962d300f3de95633f7b6535e80c5ce`](https://huggingface.co/perplexity-ai/pplx-decider-v1.1-27b/blob/14c9d90137962d300f3de95633f7b6535e80c5ce/README.md) declares Apache-2.0. This is the model name returned by the tested image service; it is not a Dou Dizhu policy. No weights or inference-server source from this model are bundled here.
- **Community MLX conversion** — the [referenced artifact](https://huggingface.co/mlx-community/pplx-decider-v1.1-27b-4bit/tree/66383f28b37637658b02b8e82b1029598b138642) is an optional deployment reference, not a locally verified backend. Consult its own model card and included licensing when downloading or redistributing it.
- **Jev / TypeSafe and other hosted services** — API access is subject to the provider's terms. Protocol compatibility and a request alias such as `jev-1.13.0` do not establish the identity, license or availability of the loaded model. Record the actual response model separately.

视觉服务、策略权重与本项目代码是不同组件。项目采用 Apache-2.0 不代表拥有托管服务或 Jev 模型权重的分发授权；公开配置不提供开发者内网服务的使用权。

## Runtime dependencies / 运行依赖

License identifiers below were checked against the pinned packages' installed metadata; bundled components may carry additional notices. Refer to each distribution for its complete terms.

| Dependency | Pinned version | Declared license |
| --- | --- | --- |
| DouZero | 1.1.0 | Apache-2.0 |
| PyTorch | 2.6.0 | BSD-3-Clause |
| NumPy | 2.2.6 | BSD-3-Clause; see bundled-component notices |
| Pillow | 11.3.0 | MIT-CMU |
| Playwright | 1.58.0 | Apache-2.0; downloaded browsers have their own notices |
| GitPython | 3.1.45 | BSD-3-Clause |

macOS Vision, Swift tooling and system fonts are used from the user's platform installation; the project does not redistribute them.

## Documentation images / 文档配图

`docs/assets/external-player-flow.svg` is an original project diagram. `docs/assets/table-preview.png` is a crop of the project's synthetic test fixture `tests/fixtures/external/opening.png`, showing the included browser table at the bidding stage. These documentation assets are covered by the root project license; they contain no private endpoint, credentials or real-player information. Referenced third-party names are used for attribution, not to imply endorsement.
