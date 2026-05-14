"""modules/tier3_reasoning/imagination — Imagination Engine package.

Modules:
    TheoryBuilderModule  — orchestrates the imagination cycle
    CriticModule         — evaluates and ranks theories
    CounterfactualModule — generates "what if" alternatives

Services (not CognitiveModules):
    HypothesisEngine     — generates competing theories via LLMRouter
    ScenarioSimulator    — simulates future outcomes for each theory
    IdeaMemory           — persists theories to ~/.jarvis_brain/idea_memory.json

Shared data structures:
    Theory               — defined in hypothesis_engine.py
    Scenario             — defined in scenario_simulator.py
"""
from modules.tier3_reasoning.imagination.hypothesis_engine import Theory, HypothesisEngine
from modules.tier3_reasoning.imagination.scenario_simulator import Scenario, ScenarioSimulator
from modules.tier3_reasoning.imagination.idea_memory import IdeaMemory
from modules.tier3_reasoning.imagination.critic import CriticModule
from modules.tier3_reasoning.imagination.counterfactuals import CounterfactualModule
from modules.tier3_reasoning.imagination.theory_builder import TheoryBuilderModule

__all__ = [
    "Theory",
    "Scenario",
    "HypothesisEngine",
    "ScenarioSimulator",
    "IdeaMemory",
    "TheoryBuilderModule",
    "CriticModule",
    "CounterfactualModule",
]
