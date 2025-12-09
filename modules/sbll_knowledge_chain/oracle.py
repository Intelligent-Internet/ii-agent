import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

class TruthOracle:
    """
    The Retrieval Layer: Allows II-Agents to query the SBLL Blockchain
    for verified philosophical truth.
    """
    def __init__(self, blockchain_instance):
        self.blockchain = blockchain_instance

    def seek_wisdom(self, query_topic: str, min_confidence: int = 0, specific_tradition: str = None) -> Dict:
        """
        Scans the immutable chain for insights related to a topic.
        """
        logger.info(f"Oracle Query: '{query_topic}' (Min Conf: {min_confidence})")
        
        results = []
        
        for block in self.blockchain.chain:
            content_pool = block['data'].get('insights', []) + block['data'].get('claims', [])
            
            for item in content_pool:
                if query_topic.lower() in item['content'].lower():
                    
                    item_confidence = item.get('truth_confidence', item.get('confidence_score', 0))
                    item_tradition = item.get('tradition', 'UNIVERSAL')
                    
                    if item_confidence >= min_confidence:
                        if specific_tradition is None or specific_tradition == item_tradition:
                            alignment = item.get('cosmic_alignment', item.get('reality_contact', 0))
                            relevance_score = item_confidence + (alignment * 0.5)
                            
                            results.append({
                                'content': item['content'],
                                'source_block': block['index'],
                                'tradition': item_tradition,
                                'confidence': item_confidence,
                                'score': relevance_score,
                                'type': 'INSIGHT' if 'tradition' in item else 'CLAIM'
                            })

        results.sort(key=lambda x: x['score'], reverse=True)
        logger.debug(f"Oracle found {len(results)} matches for '{query_topic}'")
        
        return {
            'query': query_topic,
            'total_found': len(results),
            'top_results': results[:3]
        }

    def synthesize_answer(self, oracle_result: Dict) -> str:
        if oracle_result['total_found'] == 0:
            return "The Oracle is silent. No verified truth found on this topic."

        synthesis = f"Verified Wisdom ({oracle_result['total_found']} records found):\n"
        for idx, res in enumerate(oracle_result['top_results']):
            icon = "🧘" if res['type'] == 'INSIGHT' else "🔬"
            synthesis += f"\n{idx+1}. {icon} [{res['tradition']}] (Conf: {res['confidence']})\n"
            synthesis += f"   \"{res['content']}\"\n"
            synthesis += f"   (Source: Block #{res['source_block']})\n"
            
        return synthesis
