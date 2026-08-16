"""Genetic Algorithm strategy optimizer for loom-ai.

Evolves strategy parameter sets (model weights, temperature, top_p) to
maximise a caller-supplied fitness function.  Uses only the standard
library -- no external dependencies required.

Classes
-------
Individual       -- a single candidate parameter set with fitness
GeneticOptimizer -- population-based GA with selection, crossover, and mutation
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Individual:
    """A candidate solution in the GA population.

    ``genes`` is a dict mapping parameter names to float values.
    ``fitness`` stores the most recent evaluation score (higher is better).
    """

    genes: dict[str, float] = field(default_factory=dict)
    fitness: float = 0.0


# -- Parameter bounds ---------------------------------------------------


@dataclass
class ParamBounds:
    """Min/max range for a single evolvable parameter."""

    name: str
    low: float
    high: float


# -- Default parameter space --------------------------------------------

DEFAULT_PARAMS: list[ParamBounds] = [
    ParamBounds("temperature", 0.0, 2.0),
    ParamBounds("top_p", 0.0, 1.0),
    ParamBounds("model_weight", 0.0, 1.0),
]


# -- GeneticOptimizer ---------------------------------------------------


class GeneticOptimizer:
    """Simple genetic algorithm for evolving strategy parameters.

    The optimizer maintains a fixed-size population of
    :class:`Individual` instances.  Each generation:

    1. **Selection** -- tournament selection picks parents
    2. **Crossover** -- uniform crossover produces offspring
    3. **Mutation** -- Gaussian perturbation of random genes
    4. **Replacement** -- offspring replace lowest-fitness members

    The caller drives evolution by calling :meth:`evolve` with a
    fitness function that scores an :class:`Individual`.
    """

    def __init__(
        self,
        *,
        params: list[ParamBounds] | None = None,
        population_size: int = 20,
        mutation_rate: float = 0.1,
        mutation_sigma: float = 0.1,
        crossover_rate: float = 0.7,
        tournament_size: int = 3,
        elitism: int = 1,
    ) -> None:
        if population_size < 2:
            raise ValueError("population_size must be >= 2")
        if elitism >= population_size:
            raise ValueError("elitism must be less than population_size")
        self.params = params or list(DEFAULT_PARAMS)
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.mutation_sigma = mutation_sigma
        self.crossover_rate = crossover_rate
        self.tournament_size = min(tournament_size, population_size)
        self.elitism = elitism
        self.population: list[Individual] = []
        self.generation: int = 0
        self._best: Individual | None = None

    # -- Initialisation --------------------------------------------------

    def initialize(self) -> None:
        """Create a random initial population."""
        self.population = [
            self._random_individual() for _ in range(self.population_size)
        ]
        self.generation = 0
        self._best = None

    def _random_individual(self) -> Individual:
        """Return an individual with uniformly sampled gene values."""
        genes = {p.name: random.uniform(p.low, p.high) for p in self.params}
        return Individual(genes=genes)

    # -- Core GA loop ----------------------------------------------------

    def evolve(
        self,
        fitness_fn: Callable[[Individual], float],
        *,
        generations: int = 1,
    ) -> Individual:
        """Run *generations* of evolution and return the best individual.

        Parameters
        ----------
        fitness_fn:
            A callable that takes an :class:`Individual` and returns a
            float fitness score (higher is better).
        generations:
            Number of generations to run.

        Returns
        -------
        Individual
            The best individual found across all generations.
        """
        if not self.population:
            self.initialize()

        for _ in range(generations):
            self._evaluate(fitness_fn)
            self._step()
            self.generation += 1

        # Final evaluation to make sure fitnesses are up-to-date
        self._evaluate(fitness_fn)
        return self.best

    @property
    def best(self) -> Individual:
        """Return the best individual seen so far."""
        if self._best is None:
            raise RuntimeError("No evolution has been run yet")
        return self._best

    # -- Internal GA steps -----------------------------------------------

    def _evaluate(self, fitness_fn: Callable[[Individual], float]) -> None:
        """Score every individual and track the overall best."""
        for ind in self.population:
            ind.fitness = fitness_fn(ind)
        current_best = max(self.population, key=lambda i: i.fitness)
        if self._best is None or current_best.fitness > self._best.fitness:
            self._best = Individual(
                genes=dict(current_best.genes),
                fitness=current_best.fitness,
            )

    def _step(self) -> None:
        """Perform one generation of selection, crossover, mutation."""
        # Sort by fitness descending
        ranked = sorted(self.population, key=lambda i: i.fitness, reverse=True)

        # Elitism: keep top individuals
        new_pop: list[Individual] = [
            Individual(genes=dict(ind.genes), fitness=ind.fitness)
            for ind in ranked[: self.elitism]
        ]

        # Fill rest via selection + crossover + mutation
        while len(new_pop) < self.population_size:
            p1 = self._tournament_select()
            p2 = self._tournament_select()

            if random.random() < self.crossover_rate:
                c1, c2 = self._crossover(p1, p2)
            else:
                c1 = Individual(genes=dict(p1.genes))
                c2 = Individual(genes=dict(p2.genes))

            self._mutate(c1)
            self._mutate(c2)

            new_pop.append(c1)
            if len(new_pop) < self.population_size:
                new_pop.append(c2)

        self.population = new_pop

    def _tournament_select(self) -> Individual:
        """Select one individual via tournament selection."""
        contestants = random.sample(self.population, self.tournament_size)
        return max(contestants, key=lambda i: i.fitness)

    def _crossover(
        self, p1: Individual, p2: Individual
    ) -> tuple[Individual, Individual]:
        """Uniform crossover: each gene randomly from one parent."""
        c1_genes: dict[str, float] = {}
        c2_genes: dict[str, float] = {}
        for p in self.params:
            if random.random() < 0.5:
                c1_genes[p.name] = p1.genes[p.name]
                c2_genes[p.name] = p2.genes[p.name]
            else:
                c1_genes[p.name] = p2.genes[p.name]
                c2_genes[p.name] = p1.genes[p.name]
        return Individual(genes=c1_genes), Individual(genes=c2_genes)

    def _mutate(self, ind: Individual) -> None:
        """Apply Gaussian mutation to each gene with probability mutation_rate."""
        bounds = {p.name: p for p in self.params}
        for name in ind.genes:
            if random.random() < self.mutation_rate:
                delta = random.gauss(0, self.mutation_sigma)
                new_val = ind.genes[name] + delta
                b = bounds[name]
                ind.genes[name] = max(b.low, min(b.high, new_val))

    # -- Utilities -------------------------------------------------------

    def population_stats(self) -> dict[str, float]:
        """Return summary statistics for the current population."""
        if not self.population:
            return {"min": 0.0, "max": 0.0, "mean": 0.0, "std": 0.0}
        fits = [i.fitness for i in self.population]
        n = len(fits)
        mean = sum(fits) / n
        variance = sum((f - mean) ** 2 for f in fits) / n
        return {
            "min": min(fits),
            "max": max(fits),
            "mean": mean,
            "std": math.sqrt(variance),
        }

    def diversity(self) -> float:
        """Return gene-space diversity as mean pairwise distance.

        Returns 0.0 for populations of size 0 or 1.
        """
        n = len(self.population)
        if n < 2:
            return 0.0
        total = 0.0
        pairs = 0
        for i in range(n):
            for j in range(i + 1, n):
                dist = sum(
                    (
                        self.population[i].genes[p.name]
                        - self.population[j].genes[p.name]
                    )
                    ** 2
                    for p in self.params
                )
                total += math.sqrt(dist)
                pairs += 1
        return total / pairs
