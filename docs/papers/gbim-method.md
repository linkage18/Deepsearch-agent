# Graph Bayesian Optimization for Influence Maximization: A Surrogate Model Approach

## Abstract
This paper introduces GBIM, a graph Bayesian optimization framework for influence maximization in multiplex networks. Traditional IM methods require expensive Monte Carlo simulations to estimate influence spread. GBIM replaces these simulations with a learned surrogate model based on graph neural networks with kernelized attention mechanisms.

## Key Method
GBIM uses a two-module architecture: (1) **Surrogate Model**: a Global Kernelized Attention Message-Passing network that learns the multiplex diffusion process and serves as a non-linear basis function for Bayesian linear regression, (2) **Data Acquisition**: an explore-exploit strategy using upper confidence bound to sample candidate seed sets. The surrogate model captures both node-level features and cross-layer propagation patterns.

## Key Finding
The kernelized attention mechanism allows the surrogate model to handle heterogeneous diffusion across layers, while Bayesian linear regression provides uncertainty estimates for exploration. This reduces the number of expensive Monte Carlo evaluations from thousands to hundreds.

## Advantages
- Reduces computational cost by 10-100x compared to greedy methods
- Handles multiplex networks with diverse propagation models
- Provides uncertainty quantification for seed selection decisions
