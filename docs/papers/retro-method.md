# RETRO: Improving Language Models by Retrieving from Trillions of Tokens

## Abstract
RETRO (Retrieval-Enhanced Transformer) augments auto-regressive language models with a retrieval mechanism that accesses a massive database of trillions of tokens. Unlike standard language models that rely solely on parametric knowledge, RETRO retrieves relevant text chunks at each generation step and conditions predictions on both the context and retrieved neighbors.

## Key Method
RETRO uses a chunked cross-attention mechanism: (1) the input text is divided into fixed-size chunks, (2) for each chunk, the model retrieves the k nearest neighbors from a database indexed by a frozen BERT-style encoder, (3) cross-attention layers attend to both the retrieved neighbors and the standard decoder context. The retrieval database contains 2 trillion tokens from MassiveText.

## Experimental Results
RETRO achieves GPT-3-level perplexity with 4x fewer parameters (7.5B vs 175B). On question answering, it outperforms similarly sized GPT models by 10-15%. The retrieval mechanism provides a direct path for updating knowledge without retraining.

## Key Insight
Explicit retrieval augments parametric knowledge with dynamic access to external information, making models more parameter-efficient and easier to update. The chunked cross-attention design ensures that retrieval influences generation at every step.

## Limitations
- Requires large pre-built retrieval database
- Frozen encoder cannot adapt to query distribution shifts
- Retrieval latency adds to inference time
