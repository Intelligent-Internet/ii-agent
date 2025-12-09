import logging
from typing import Dict, Any
from .chain import SBBLBlockchain
from .oracle import TruthOracle

logger = logging.getLogger(__name__)

class KnowledgeChainTool:
    """
    The Interface that allows II-Agent to interact with the 
    Philosophical Blockchain.
    """
    def __init__(self):
        self.blockchain = SBBLBlockchain()
        # Attempt to load existing state
        try:
            self.blockchain.load_chain_state()
        except Exception as e:
            logger.warning(f"Could not load existing ledger, starting fresh. Reason: {e}")
            
        self.oracle = TruthOracle(self.blockchain)

    def name(self) -> str:
        return "knowledge_blockchain"

    def description(self) -> str:
        return (
            "Use this tool to either STORE verified philosophical insights "
            "or QUERY the immutable ledger for high-confidence truth. "
            "Actions: 'contribute' or 'query'."
        )

    def run(self, action: str, content: str, tradition: str = "MODERN_SCIENTIFIC") -> str:
        """
        Main entry point for the Agent.
        """
        logger.info(f"Agent Action: {action} | Content: {content[:20]}...")
        
        if action == "contribute":
            insight = {
                'content': content,
                'tradition': tradition,
                'truth_confidence': 200,
                'cosmic_alignment': 200
            }
            
            self.blockchain.add_philosophical_insight(insight)
            new_block = self.blockchain.mine_block()
            self.blockchain.save_chain_state()
            
            if new_block:
                return f"Success: Insight anchored in Block #{new_block['index']} (Hash: {new_block['hash'][:8]}...)"
            else:
                return "Mining deferred: Not enough entropy."

        elif action == "query":
            results = self.oracle.seek_wisdom(content, min_confidence=150)
            return self.oracle.synthesize_answer(results)

        else:
            return "Error: Unknown action. Use 'contribute' or 'query'."
