# Toolformer: Language Models Can Teach Themselves to Use Tools

## Abstract
Toolformer introduces a self-supervised approach for language models to learn tool use through API calls. The model is trained to decide when and how to call external tools (calculator, search engine, translation system, calendar) by augmenting the training data with API call annotations.

## Key Method
The training process consists of: (1) **Sampling**: for each position in a text, the model samples potential API calls using few-shot examples, (2) **Filtering**: calls that reduce the loss on subsequent tokens are retained, (3) **Fine-tuning**: the original LM is fine-tuned on the augmented corpus containing API calls and their responses. This requires no human annotation or reinforcement learning.

## Experimental Results
Toolformer significantly improves zero-shot performance on tasks requiring tool use: QA (+23%), math (+35%), and temporal reasoning (+18%). The model learns to use each tool appropriately without explicit supervision of when to call which tool.

## Limitations
- Toolformer uses frozen API calls without execution feedback loops
- Cannot adapt tool use based on partial results
- Limited to atomic tool calls rather than multi-step tool chains

## Impact
Toolformer demonstrated that language models can autonomously learn tool use through self-supervision, paving the way for tool-augmented language models.
