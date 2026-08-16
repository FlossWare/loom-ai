"""Tests for loom_ai.backends.genetic_optimizer."""

import random

import pytest

from loom_ai.backends.genetic_optimizer import (
    GeneticOptimizer,
    Individual,
    ParamBounds,
)

# ── Initialisation ─────────────────────────────────────────────────────


def test_initialize_creates_population():
    opt = GeneticOptimizer(population_size=10)
    opt.initialize()
    assert len(opt.population) == 10
    assert opt.generation == 0


def test_initialize_respects_bounds():
    params = [ParamBounds("x", 0.0, 1.0), ParamBounds("y", -5.0, 5.0)]
    opt = GeneticOptimizer(params=params, population_size=50)
    opt.initialize()
    for ind in opt.population:
        assert 0.0 <= ind.genes["x"] <= 1.0
        assert -5.0 <= ind.genes["y"] <= 5.0


def test_default_params_used():
    opt = GeneticOptimizer()
    opt.initialize()
    for ind in opt.population:
        assert set(ind.genes.keys()) == {"temperature", "top_p", "model_weight"}


def test_population_size_validation():
    with pytest.raises(ValueError, match="population_size must be >= 2"):
        GeneticOptimizer(population_size=1)


def test_elitism_validation():
    with pytest.raises(ValueError, match="elitism must be less than population_size"):
        GeneticOptimizer(population_size=5, elitism=5)


# ── Evolution ──────────────────────────────────────────────────────────


def test_evolve_returns_best():
    random.seed(42)
    params = [ParamBounds("x", 0.0, 10.0)]
    opt = GeneticOptimizer(params=params, population_size=20)

    def fitness(ind: Individual) -> float:
        # Maximise at x=5 (inverted parabola)
        return -((ind.genes["x"] - 5.0) ** 2)

    best = opt.evolve(fitness, generations=50)
    # Should get close to x=5
    assert abs(best.genes["x"] - 5.0) < 1.0
    assert best.fitness > -1.0


def test_evolve_improves_over_generations():
    random.seed(123)
    params = [ParamBounds("x", 0.0, 10.0)]
    opt = GeneticOptimizer(params=params, population_size=20)

    def fitness(ind: Individual) -> float:
        return -((ind.genes["x"] - 7.0) ** 2)

    best_gen1 = opt.evolve(fitness, generations=1)
    fit1 = best_gen1.fitness

    best_gen50 = opt.evolve(fitness, generations=49)
    fit50 = best_gen50.fitness

    assert fit50 >= fit1


def test_evolve_tracks_generation_count():
    opt = GeneticOptimizer(population_size=10)
    opt.evolve(lambda ind: sum(ind.genes.values()), generations=5)
    assert opt.generation == 5


def test_evolve_auto_initializes():
    """evolve initializes population if not already done."""
    opt = GeneticOptimizer(population_size=10)
    assert len(opt.population) == 0
    opt.evolve(lambda ind: 1.0, generations=1)
    assert len(opt.population) == 10


def test_best_raises_before_evolve():
    opt = GeneticOptimizer()
    with pytest.raises(RuntimeError, match="No evolution has been run"):
        _ = opt.best


# ── Crossover ──────────────────────────────────────────────────────────


def test_crossover_produces_children_with_parent_genes():
    random.seed(0)
    params = [ParamBounds("a", 0.0, 1.0), ParamBounds("b", 0.0, 1.0)]
    opt = GeneticOptimizer(params=params, population_size=4)
    p1 = Individual(genes={"a": 0.1, "b": 0.2})
    p2 = Individual(genes={"a": 0.8, "b": 0.9})
    c1, c2 = opt._crossover(p1, p2)
    # Each child gene must come from one parent
    for name in ["a", "b"]:
        assert c1.genes[name] in (p1.genes[name], p2.genes[name])
        assert c2.genes[name] in (p1.genes[name], p2.genes[name])


# ── Mutation ───────────────────────────────────────────────────────────


def test_mutation_stays_within_bounds():
    random.seed(42)
    params = [ParamBounds("x", 0.0, 1.0)]
    opt = GeneticOptimizer(params=params, mutation_rate=1.0, mutation_sigma=10.0)
    ind = Individual(genes={"x": 0.5})
    for _ in range(100):
        opt._mutate(ind)
        assert 0.0 <= ind.genes["x"] <= 1.0


def test_zero_mutation_rate_no_change():
    params = [ParamBounds("x", 0.0, 1.0)]
    opt = GeneticOptimizer(params=params, mutation_rate=0.0)
    ind = Individual(genes={"x": 0.5})
    opt._mutate(ind)
    assert ind.genes["x"] == 0.5


# ── Population stats ──────────────────────────────────────────────────


def test_population_stats_empty():
    opt = GeneticOptimizer()
    stats = opt.population_stats()
    assert stats["min"] == 0.0
    assert stats["max"] == 0.0
    assert stats["mean"] == 0.0
    assert stats["std"] == 0.0


def test_population_stats_after_evolve():
    random.seed(42)
    opt = GeneticOptimizer(population_size=10)
    opt.evolve(lambda ind: ind.genes.get("temperature", 0.0), generations=1)
    stats = opt.population_stats()
    assert stats["max"] >= stats["min"]
    assert stats["min"] <= stats["mean"] <= stats["max"]
    assert stats["std"] >= 0.0


# ── Diversity ──────────────────────────────────────────────────────────


def test_diversity_empty():
    opt = GeneticOptimizer()
    assert opt.diversity() == 0.0


def test_diversity_single_individual():
    opt = GeneticOptimizer(population_size=2)
    opt.population = [Individual(genes={"x": 0.5})]
    assert opt.diversity() == 0.0


def test_diversity_identical_population():
    params = [ParamBounds("x", 0.0, 1.0)]
    opt = GeneticOptimizer(params=params, population_size=5)
    opt.population = [Individual(genes={"x": 0.5}) for _ in range(5)]
    assert opt.diversity() == 0.0


def test_diversity_different_population():
    params = [ParamBounds("x", 0.0, 1.0)]
    opt = GeneticOptimizer(params=params, population_size=2)
    opt.population = [
        Individual(genes={"x": 0.0}),
        Individual(genes={"x": 1.0}),
    ]
    assert opt.diversity() == 1.0


# ── Determinism ────────────────────────────────────────────────────────


def test_deterministic_with_seed():
    params = [ParamBounds("x", 0.0, 10.0)]

    opt1 = GeneticOptimizer(params=params, population_size=10, seed=99)
    best1 = opt1.evolve(lambda i: -abs(i.genes["x"] - 3.0), generations=10)

    opt2 = GeneticOptimizer(params=params, population_size=10, seed=99)
    best2 = opt2.evolve(lambda i: -abs(i.genes["x"] - 3.0), generations=10)

    assert best1.genes["x"] == best2.genes["x"]
    assert best1.fitness == best2.fitness


# ── Elitism ────────────────────────────────────────────────────────────


def test_elitism_preserves_best():
    random.seed(42)
    params = [ParamBounds("x", 0.0, 10.0)]
    opt = GeneticOptimizer(params=params, population_size=10, elitism=2)

    def fitness(ind: Individual) -> float:
        return ind.genes["x"]

    opt.evolve(fitness, generations=1)
    gen1_best = opt.best.fitness

    opt.evolve(fitness, generations=1)
    gen2_best = opt.best.fitness

    # With elitism, best should never decrease
    assert gen2_best >= gen1_best


# ── Multi-parameter optimisation ──────────────────────────────────────


def test_multi_param_optimization():
    random.seed(42)
    params = [
        ParamBounds("x", -5.0, 5.0),
        ParamBounds("y", -5.0, 5.0),
    ]
    opt = GeneticOptimizer(params=params, population_size=30)

    def fitness(ind: Individual) -> float:
        # Maximum at (2, -1)
        return -((ind.genes["x"] - 2.0) ** 2 + (ind.genes["y"] + 1.0) ** 2)

    best = opt.evolve(fitness, generations=100)
    assert abs(best.genes["x"] - 2.0) < 1.5
    assert abs(best.genes["y"] + 1.0) < 1.5
