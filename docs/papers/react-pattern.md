# ReAct: Synergizing Reasoning and Acting in Language Models

## Abstract
We present ReAct, a paradigm that combines reasoning traces and task-specific actions in an interleaved manner for large language models. By generating both verbal reasoning traces (e.g., "I need to search for X") and actions (e.g., calling a search API), ReAct enables models to dynamically reason about what information is needed, act to acquire it, and refine subsequent reasoning based on observations. This approach addresses key limitations of pure chain-of-thought reasoning, particularly in handling incomplete information and adapting to external feedback.

## Key Method
ReAct alternates between two modes: (1) **Thought**: generating natural language reasoning about the current state and next steps, (2) **Act**: invoking external tools such as search or calculation APIs. The model observes the tool output and continues the thought-action loop until a final answer is reached.

## Experimental Results
On HotpotQA, ReAct achieves an EM score of 34.6 and F1 of 58.9, outperforming standard prompting (20.4/33.7) and chain-of-thought (26.4/48.7). On Fever, ReAct achieves 62.5% accuracy vs CoT's 55.4%.

## Conclusion
ReAct demonstrates that explicit reasoning traces combined with tool use improves both interpretability and correctness in knowledge-intensive tasks.
