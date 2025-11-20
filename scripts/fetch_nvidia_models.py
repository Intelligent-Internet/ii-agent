#!/usr/bin/env python3
"""Fetch NVIDIA models and rank them using Bayesian inference."""
import os
import sys
import json
import httpx
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict


class BayesianModelRanker:
    """Rank models using Bayesian inference based on metadata signals."""

    def __init__(self):
        # Prior beliefs about model quality indicators
        self.quality_signals = {
            'name_patterns': {
                'high': ['instruct', 'chat', 'plus', 'pro', 'turbo', 'ultra'],
                'medium': ['base', 'v2', 'v3'],
                'low': ['preview', 'alpha', 'beta', 'test']
            },
            'size_indicators': {
                'high': ['405b', '480b', '405B', '480B', '70b', '72b'],
                'medium': ['7b', '8b', '13b', '34b'],
                'low': ['1b', '3b']
            },
            'provider_quality': {
                'high': ['meta', 'mistralai', 'deepseek', 'qwen'],
                'medium': ['nvidia', 'google'],
                'low': []
            }
        }

        # Bayesian priors (probability of being high quality)
        self.prior_quality = 0.5  # Neutral prior

    def calculate_posterior(self, model: Dict[str, Any]) -> float:
        """Calculate posterior probability using Bayesian inference."""
        model_id = model.get('id', '')
        model_name = model_id.lower()

        # Start with prior
        posterior = self.prior_quality

        # Update based on name patterns (likelihood)
        name_likelihood = self._assess_name_quality(model_name)
        posterior = self._bayesian_update(posterior, name_likelihood)

        # Update based on size indicators
        size_likelihood = self._assess_size_quality(model_name)
        posterior = self._bayesian_update(posterior, size_likelihood)

        # Update based on provider
        provider_likelihood = self._assess_provider_quality(model_name)
        posterior = self._bayesian_update(posterior, provider_likelihood)

        # Update based on recency (if created timestamp available)
        if model.get('created'):
            recency_likelihood = self._assess_recency(model['created'])
            posterior = self._bayesian_update(posterior, recency_likelihood)

        return posterior

    def _assess_name_quality(self, name: str) -> float:
        """Assess quality based on name patterns."""
        high_count = sum(1 for pattern in self.quality_signals['name_patterns']['high'] if pattern in name)
        low_count = sum(1 for pattern in self.quality_signals['name_patterns']['low'] if pattern in name)

        if high_count > 0 and low_count == 0:
            return 0.8  # High likelihood of quality
        elif low_count > 0:
            return 0.2  # Low likelihood of quality
        else:
            return 0.5  # Neutral

    def _assess_size_quality(self, name: str) -> float:
        """Assess quality based on model size indicators."""
        for size in self.quality_signals['size_indicators']['high']:
            if size in name:
                return 0.9
        for size in self.quality_signals['size_indicators']['medium']:
            if size in name:
                return 0.6
        for size in self.quality_signals['size_indicators']['low']:
            if size in name:
                return 0.3
        return 0.5  # No size info

    def _assess_provider_quality(self, name: str) -> float:
        """Assess quality based on provider."""
        for provider in self.quality_signals['provider_quality']['high']:
            if name.startswith(provider):
                return 0.7
        for provider in self.quality_signals['provider_quality']['medium']:
            if name.startswith(provider):
                return 0.5
        return 0.4

    def _assess_recency(self, created_timestamp: int) -> float:
        """Assess quality based on recency (newer = better)."""
        if not created_timestamp:
            return 0.5

        # Models created in last year are likely better
        current_time = datetime.now().timestamp()
        age_days = (current_time - created_timestamp) / 86400

        if age_days < 180:  # < 6 months
            return 0.8
        elif age_days < 365:  # < 1 year
            return 0.6
        else:
            return 0.4

    def _bayesian_update(self, prior: float, likelihood: float) -> float:
        """Bayesian update: P(H|E) = P(E|H) * P(H) / P(E)."""
        # Simplified Bayesian update
        # P(E) = P(E|H)*P(H) + P(E|¬H)*P(¬H)
        p_e_not_h = 1 - likelihood
        p_e = likelihood * prior + p_e_not_h * (1 - prior)

        if p_e == 0:
            return prior

        posterior = (likelihood * prior) / p_e
        return min(max(posterior, 0.0), 1.0)  # Clamp to [0, 1]


def fetch_nvidia_models(api_key: str) -> List[Dict[str, Any]]:
    """Fetch models from NVIDIA API."""
    url = "https://integrate.api.nvidia.com/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    print(f"Fetching models from {url}...")

    with httpx.Client() as client:
        response = client.get(url, headers=headers, timeout=30.0)

        if response.status_code != 200:
            print(f"Error: HTTP {response.status_code}")
            print(response.text)
            sys.exit(1)

        data = response.json()
        models = data.get("data", [])

        # Filter out deployment-specific models (those with / in id)
        models = [m for m in models if "/" in m.get("id", "")]

        print(f"Found {len(models)} models")
        return models


def rank_models(models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rank models using Bayesian inference."""
    ranker = BayesianModelRanker()

    ranked_models = []
    for model in models:
        score = ranker.calculate_posterior(model)
        ranked_model = {
            **model,
            'bayesian_score': score,
            'rank_metadata': {
                'scoring_method': 'bayesian_inference',
                'timestamp': datetime.now().isoformat(),
            }
        }
        ranked_models.append(ranked_model)

    # Sort by Bayesian score descending
    ranked_models.sort(key=lambda x: x['bayesian_score'], reverse=True)

    # Add rank numbers
    for i, model in enumerate(ranked_models):
        model['rank'] = i + 1

    return ranked_models


def categorize_models(models: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Categorize models by type."""
    categories = defaultdict(list)

    for model in models:
        model_id = model.get('id', '').lower()

        # Categorization logic
        if 'coder' in model_id or 'code' in model_id:
            categories['code'].append(model)
        elif 'chat' in model_id or 'instruct' in model_id:
            categories['chat'].append(model)
        elif 'embed' in model_id or 'embedding' in model_id:
            categories['embedding'].append(model)
        elif 'vision' in model_id or 'image' in model_id:
            categories['vision'].append(model)
        else:
            categories['general'].append(model)

    return dict(categories)


def save_models(models: List[Dict[str, Any]], output_file: str):
    """Save ranked models to JSON file."""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Categorize models
    categorized = categorize_models(models)

    output_data = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'total_models': len(models),
            'scoring_method': 'bayesian_inference',
            'categories': {cat: len(mods) for cat, mods in categorized.items()}
        },
        'ranked_models': models[:50],  # Top 50
        'categories': categorized,
        'all_models': models
    }

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n✓ Saved {len(models)} ranked models to {output_file}")


def print_summary(models: List[Dict[str, Any]]):
    """Print summary of top models."""
    print("\n" + "=" * 80)
    print("TOP 20 NVIDIA MODELS (Bayesian Ranking)")
    print("=" * 80)
    print(f"{'Rank':<6} {'Score':<8} {'Model ID':<50} {'Category'}")
    print("-" * 80)

    for model in models[:20]:
        rank = model.get('rank', 0)
        score = model.get('bayesian_score', 0)
        model_id = model.get('id', '')

        # Determine category
        model_lower = model_id.lower()
        if 'coder' in model_lower:
            category = 'CODE'
        elif 'chat' in model_lower or 'instruct' in model_lower:
            category = 'CHAT'
        elif 'embed' in model_lower:
            category = 'EMBED'
        else:
            category = 'GENERAL'

        print(f"{rank:<6} {score:<8.4f} {model_id:<50} {category}")

    print("=" * 80)


def main():
    """Main entry point."""
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        print("Error: NVIDIA_API_KEY environment variable not set")
        sys.exit(1)

    # Fetch models
    models = fetch_nvidia_models(api_key)

    # Rank models
    ranked_models = rank_models(models)

    # Print summary
    print_summary(ranked_models)

    # Save to file
    output_file = "data/nvidia_models_ranked.json"
    save_models(ranked_models, output_file)

    # Print statistics
    categories = categorize_models(ranked_models)
    print(f"\nModel Categories:")
    for cat, mods in categories.items():
        print(f"  {cat.upper():<12} {len(mods):>4} models")

    # Print top recommended models per category
    print(f"\nTop Recommended Models by Category:")
    for cat, mods in categories.items():
        if mods:
            top_model = mods[0]
            print(f"  {cat.upper():<12} {top_model['id']} (score: {top_model['bayesian_score']:.4f})")


if __name__ == "__main__":
    main()
