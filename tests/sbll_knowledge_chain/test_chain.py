import pytest
import os
from modules.sbll_knowledge_chain.chain import SBBLBlockchain, QuantumPhilosophicalEncoder
from modules.sbll_knowledge_chain.oracle import TruthOracle
from modules.sbll_knowledge_chain.tool_wrapper import KnowledgeChainTool

def test_blockchain_genesis():
    chain = SBBLBlockchain()
    assert len(chain.chain) == 1
    assert chain.chain[0]['index'] == 0
    assert chain.chain[0]['data']['block_type'] == 'GENESIS'

def test_add_and_mine_insight():
    chain = SBBLBlockchain()
    chain.add_philosophical_insight({
        'content': 'Test insight',
        'tradition': 'MODERN_SCIENTIFIC',
        'truth_confidence': 210,
        'cosmic_alignment': 180
    })
    block = chain.mine_block()
    assert block is not None
    assert block['index'] == 1
    assert block['data']['insights'][0]['content'] == 'Test insight'

def test_oracle_query():
    chain = SBBLBlockchain()
    chain.add_philosophical_insight({
        'content': 'Wisdom of change',
        'tradition': 'EASTERN_TAOIST',
        'truth_confidence': 220,
        'cosmic_alignment': 200
    })
    chain.mine_block()
    oracle = TruthOracle(chain)
    result = oracle.seek_wisdom('change', min_confidence=200)
    assert result['total_found'] == 1
    assert 'Wisdom of change' in result['top_results'][0]['content']
    answer = oracle.synthesize_answer(result)
    assert 'Verified Wisdom' in answer

def test_tool_wrapper_contribute_and_query(tmp_path):
    # Use a temp ledger file to avoid polluting workspace
    ledger_file = tmp_path / 'sbll_ledger.json'
    tool = KnowledgeChainTool()
    tool.blockchain.save_chain_state(str(ledger_file))
    res = tool.run('contribute', 'Knowledge is justified true belief.', tradition='WESTERN_ANALYTIC')
    assert 'Success' in res
    query = tool.run('query', 'justified')
    assert 'Verified Wisdom' in query
    # Clean up
    if os.path.exists(ledger_file):
        os.remove(ledger_file)

def test_encoder_hash_and_compression():
    encoder = QuantumPhilosophicalEncoder()
    content = 'The only constant is change.'
    h = encoder._quantum_hash(content)
    assert isinstance(h, str) and len(h) == 32
    ratio = encoder._calculate_compression(content)
    assert ratio > 0
