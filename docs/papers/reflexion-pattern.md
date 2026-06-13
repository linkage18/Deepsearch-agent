# Reflexion: Language Agents with Verbal Reinforcement Learning

## Abstract
Reflexion introduces a novel framework that converts environmental feedback into linguistic summary memories, enabling agents to learn from past mistakes without expensive gradient updates. The agent stores successful and failed trajectories as natural language "reflections" in episodic memory, and uses these reflections to guide future decisions.

## Key Method
The Reflexion architecture consists of three components: (1) **Actor**: a policy that generates actions based on current state and memory, (2) **Evaluator**: a function that scores the Actor's trajectory, (3) **Memory**: a persistent store of reflections (natural language summaries of past successes and failures). When the Actor encounters a similar situation, relevant reflections are retrieved from memory and injected into the prompt.

## Experimental Results
On the AlfWorld benchmark, Reflexion improves the success rate from 58% to 80% compared to the baseline ReAct agent. On HotpotQA, it achieves 61% accuracy vs ReAct's 47%. The key insight is that while ReAct learns only within a single episode, Reflexion transfers knowledge across episodes via linguistic memory.

## Conclusion
Verbal reinforcement learning through reflection enables more sample-efficient learning in interactive environments by leveraging language as a compressed representation of experience.
