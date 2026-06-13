# Generative Agents: Interactive Simulacra of Human Behavior

## Abstract
Generative Agents introduce a multi-agent architecture where LLM-powered agents simulate believable human behavior in interactive environments. Each agent maintains a comprehensive memory stream, reflects on past experiences to form higher-level insights, and plans future actions based on their reflections and current state.

## Key Method
The architecture consists of: (1) **Memory Stream**: a chronological record of experiences with recency, importance, and relevance weights, (2) **Reflection**: periodic synthesis of higher-level insights from the memory stream using LLM queries, (3) **Planning**: hierarchical action planning where high-level plans are decomposed into moment-by-moment actions. Agents retrieve relevant memories and reflections when deciding how to act.

## Experimental Results
In a simulated town environment with 25 agents, generative agents produce emergent social behaviors: organizing parties, forming opinions about other agents, coordinating activities without explicit instructions. Human evaluators rated agent behavior as believable 76% of the time.

## Key Insight
The memory-reflection-planning loop enables agents to maintain consistent personality and adapt behavior based on accumulated experience, without requiring explicit social rules or scripts.

## Applications
- Social simulation for policy analysis
- Interactive NPCs in games
- Training data generation for social AI
