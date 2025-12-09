"""Simple smoke test for the SBLL Knowledge Chain tool.

Runs a contribute action then a query and prints results.
"""
import logging
import os
import sys

logging.basicConfig(level=logging.INFO)

# Ensure repo root is on sys.path so we can import the module package
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from modules.sbll_knowledge_chain import KnowledgeChainTool
except Exception as e:
    print(f"Failed to import KnowledgeChainTool: {e}")
    raise

def main():
    tool = KnowledgeChainTool()

    # Contribute an insight
    contribution = "Impermanence: everything changes; all is flux."
    res = tool.run('contribute', contribution, tradition='WESTERN_ANALYTIC')
    print('Contribute result:')
    print(res)

    # Query the oracle for 'flux'
    query_res = tool.run('query', 'flux')
    print('\nQuery result:')
    print(query_res)

if __name__ == '__main__':
    main()
