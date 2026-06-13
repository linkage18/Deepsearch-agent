# Chain-of-Thought Prompting Elicits Reasoning in Large Language Models

## Abstract
Chain-of-Thought (CoT) prompting is a simple technique that elicits multi-step reasoning in large language models by providing few-shot examples of step-by-step reasoning chains. Instead of predicting the final answer directly, the model generates intermediate reasoning steps before reaching a conclusion.

## Key Method
CoT prompting requires no model fine-tuning or gradient updates. The approach constructs few-shot exemplars where each example includes: (1) a question, (2) a series of natural language reasoning steps, (3) the final answer. During inference, the model generates its own reasoning chain before producing the answer. This is compatible with standard language model decoding and requires no architectural changes.

## Experimental Results
On GSM8K math word problems, CoT improves accuracy from 10.4% (standard prompting) to 40.7% (CoT) with PaLM 540B. On SVAMP, accuracy increases from 37.3% to 58.7%. The benefit is most pronounced in tasks requiring arithmetic, commonsense, and symbolic reasoning.

## Key Insight
CoT effectively increases the computational budget allocated to reasoning by distributing reasoning across multiple tokens, allowing the model to allocate more parameters to intermediate inference steps.

## Limitations
- Does not incorporate external knowledge or tool use
- Cannot correct errors once committed in the reasoning chain
- Effectiveness diminishes for tasks that do not benefit from decomposition
