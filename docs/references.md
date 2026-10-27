# Sources I grounded on

I used these manuals, papers, and datasets to plan the simulator and PolarFire SoC work, then directed coding agents through the build. Local critics checked written claims against project files. The [method page](method.md) explains the source workflow, and the [results index](results-index.md) links the measured reports. Titles follow the notebook records; public sources have links where available.

## Microchip PolarFire SoC and VectorBlox

These came from the notebook "PolarFire SoC MSS Configurator Software and Documentation" and the earlier Icicle kit notebook.

- PolarFire SoC Icicle Kit user guide
- PolarFire SoC software development and tool flow user guide
- PolarFire custom flow user guide
- Libero SoC installation and licensing guide, release 2024.2
- PolarFire SoC MSS Configurator product page
- VectorBlox Accelerator SDK product page
- Icicle Kit Linux booting guide
- [VectorBlox SDK](https://github.com/Microchip-Vectorblox/VectorBlox-SDK) and the [VectorBlox SoC Video Kit demo](https://github.com/Microchip-Vectorblox/VectorBlox-SoC-Video-Kit-Demo)
- [Hart Software Services](https://github.com/polarfire-soc/hart-software-services)
- [Icicle Kit reference design](https://github.com/polarfire-soc/icicle-kit-reference-design)
- [Yocto BSP for PolarFire SoC](https://github.com/polarfire-soc/meta-polarfire-soc-yocto-bsp)
- [PolarFire SoC documentation](https://github.com/polarfire-soc/polarfire-soc-documentation): the Icicle Kit embedded software user guide and the guide to updating Linux on the kit
- Deploying MobileUNet to the PolarFire SoC Video Kit (article), and two VectorBlox Colab notebooks for training a CNN and converting it for the engine

My toolchain notes from these are in [planning/docs/tychon-microchip-toolchain-reference.md](../planning/docs/tychon-microchip-toolchain-reference.md).

## NV-diamond magnetometry and machine learning

These came from the notebooks on NV physics, ODMR hardware and quantum sensing.

- Sensitivity optimization for NV-diamond magnetometry (Rev. Mod. Phys.)
- Deep-neural-network-based magnetic-field acquisition method for quantum sensing with nitrogen-vacancy centers (Phys. Rev. A)
- Edge-machine-learning-assisted robust magnetometer based on randomly oriented NV ensembles in diamond
- Machine learning assisted tracking of magnetic objects using quantum diamond magnetometry
- Machine-learning based high-bandwidth magnetic sensing (2025)
- Wide-field magnetometry using nitrogen-vacancy color centers with randomly oriented micro-diamonds (2022)
- Digital twin simulations toolbox of the nitrogen-vacancy center in diamond (2025)
- Low-cost ODMR experiments with nitrogen-vacancy centers in diamonds (2025)
- Components for an inexpensive CW-ODMR NV-based magnetometer (2025)
- End-to-end variational quantum sensing
- Self-aligned multilayered nitrogen-vacancy diamond nanoparticles for high spatial resolution (Gokhale et al., 2025)
- [Quantum co-magnetometer using diamond nitrogen-vacancy centers and rubidium cells](https://arxiv.org/abs/2508.15638) (arXiv 2508.15638)

## Simulation and modelling code

- SimOS, the simulator this repository wraps, cited in the [simulator README](../workers/nv-sensor-sim/README.md)
- [QuaCCAToo](https://github.com/QISS-HZB/QuaCCAToo)
- [nvmodels](https://github.com/gadamc/nvmodels): NV-center Hamiltonian and Zeeman-spectrum notebooks
- [machineLearningMagneticSensing](https://github.com/trianam/machineLearningMagneticSensing): code for ML-based magnetic sensing
- [CUDA-Q](https://github.com/NVIDIA/cuda-quantum) and its dynamics documentation, studied for a GPU backend that is still a stub

## Public datasets the simulator loads

| Loader | Dataset | DOI |
|---|---|---|
| `zenodo_ml_scan` | ML-based magnetic sensing scan data | [10.5281/zenodo.7481960](https://doi.org/10.5281/zenodo.7481960) |
| `zenodo_zerofield` | Data for "Determining strain components in a diamond waveguide from zero-field ODMR spectra of NV- center ensembles" | [10.5281/zenodo.10629041](https://doi.org/10.5281/zenodo.10629041) |
| `harvard_lowfield` | Replication data for "All-optical photoluminescence spectra of nitrogen-vacancy ensembles in diamond at low magnetic fields" | [10.7910/DVN/6TFFPG](https://doi.org/10.7910/DVN/6TFFPG) |
| `darus_gradiometry` | Replication data for "Diamond magnetometry and gradiometry towards subpicotesla DC field measurement" | [10.18419/darus-2817](https://doi.org/10.18419/darus-2817) |
| `borealis_sbquantum` | Replication data for "Bias-field-free operation of nitrogen-vacancy ensembles in diamond for accurate vector magnetometry" | [10.5683/SP3/DRTLGW](https://doi.org/10.5683/SP3/DRTLGW) |

The loaders are in [external_datasets.py](../workers/nv-sensor-sim/src/nv_sensor_sim/datasets/external_datasets.py).
