"""Smoke test for ProductionKnowledgeChainTool (enhanced features)."""
import logging
import os
import sys

logging.basicConfig(level=logging.INFO)

# Ensure repo root is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from modules.sbll_knowledge_chain.deployment import ProductionKnowledgeChainTool
except Exception as e:
    print(f"Failed to import ProductionKnowledgeChainTool: {e}")
    raise

def main():
    tool = ProductionKnowledgeChainTool(use_optimized=True)

    # Contribute an insight using enhanced tool
    content = "Consciousness emerges from recursive computational self-modeling through constraint optimization"
    res = tool.run('contribute', content, tradition='WESTERN_ANALYTIC')
    print('Contribute result:')
    print(res)

    # Query with synthesis
    wisdom = tool.run('query', 'consciousness', min_confidence=100, synthesize=True)
    print('\nQuery result:')
    print(wisdom)

    # Analyze content
    analysis = tool.run('analyze', 'Truth is correspondence with reality through multi-method verification')
    print('\nAnalysis result:')
    print(analysis)

    # Analytics
    analytics = tool.run('analytics', '')
    print('\nAnalytics result:')
    print(analytics)

if __name__ == '__main__':
    main()
