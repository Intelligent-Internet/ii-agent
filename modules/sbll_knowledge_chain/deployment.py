"""
Deployment-ready SBLL Philosophical Blockchain
"""

import json
import time
import logging

from .chain import SBBLBlockchain
from .oracle import TruthOracle
from .tool_wrapper import KnowledgeChainTool
from .advanced_features import EnhancedKnowledgeChainTool
from .optimized_chain import OptimizedSBBLBlockchain

logger = logging.getLogger(__name__)

class ProductionKnowledgeChainTool(KnowledgeChainTool):
    """Production-ready tool with all enhancements"""
    
    def __init__(self, use_optimized: bool = True, cache_size: int = 100):
        # Initialize blockchain
        if use_optimized:
            self.blockchain = OptimizedSBBLBlockchain(cache_size=cache_size)
        else:
            self.blockchain = SBBLBlockchain()
        
        # Load existing state
        try:
            self.blockchain.load_chain_state()
        except Exception as e:
            logger.warning(f"Starting fresh blockchain. Reason: {e}")
        
        self.oracle = TruthOracle(self.blockchain)
        self.enhanced_tool = EnhancedKnowledgeChainTool()
    
    def run(self, action: str, content: str, tradition: str = "MODERN_SCIENTIFIC", **kwargs) -> str:
        """Enhanced run method with more options"""
        if action == "contribute":
            # Analyze content first
            analysis = self.enhanced_tool.analyze_content(content)
            estimated_confidence = analysis['estimated_confidence']
            
            insight = {
                'content': content,
                'tradition': tradition,
                'truth_confidence': estimated_confidence,
                'cosmic_alignment': min(255, estimated_confidence + 20),
                'semantic_density': analysis['semantic_density'],
                'inference_complexity': analysis['inference_complexity']
            }
            
            self.blockchain.add_philosophical_insight(insight)
            new_block = self.blockchain.mine_block()
            
            # Save with compression if available
            try:
                self.blockchain.save_chain_state_compressed()
            except Exception:
                # Fallback
                self.blockchain.save_chain_state()
            
            if new_block:
                return (
                    f"✅ Insight anchored in Block #{new_block['index']}\n"
                    f"   Hash: {new_block['hash'][:12]}...\n"
                    f"   Confidence: {estimated_confidence}/255\n"
                    f"   Semantic Density: {analysis['semantic_density']:.1%}"
                )
            else:
                return "⏳ Mining deferred: Accumulating more philosophical entropy"
        
        elif action == "query":
            min_confidence = kwargs.get('min_confidence', 150)
            synthesize = kwargs.get('synthesize', True)
            
            results = self.oracle.seek_wisdom(content, min_confidence=min_confidence)
            
            if synthesize and results['total_found'] > 0:
                # Get enhanced synthesis
                synthesis = self.enhanced_tool.synthesize_blockchain_wisdom(content)
                base_result = self.oracle.synthesize_answer(results)
                return f"{base_result}\n\n🔮 ENHANCED SYNTHESIS:\n{synthesis.get('synthesis', '')}"
            else:
                return self.oracle.synthesize_answer(results)
        
        elif action == "analyze":
            analysis = self.enhanced_tool.analyze_content(content)
            result = f"📊 CONTENT ANALYSIS:\n"
            result += f"• Semantic Density: {analysis['semantic_density']:.1%}\n"
            result += f"• Inference Complexity: {analysis['inference_complexity']}/10\n"
            result += f"• Estimated Confidence: {analysis['estimated_confidence']}/255\n"
            result += f"• Suggested Traditions: {', '.join(analysis['tradition_suggestions'])}"
            return result
        
        elif action == "analytics":
            analytics = self.enhanced_tool.get_blockchain_analytics()
            result = f"📈 BLOCKCHAIN ANALYTICS:\n"
            result += f"• Total Blocks: {analytics['total_blocks']}\n"
            result += f"• Total Insights: {analytics['total_insights']}\n"
            result += f"• Chain Health: {analytics['chain_health']:.1%}\n"
            result += f"• Most Prolific Tradition: {analytics['most_prolific_tradition']}\n"
            result += f"• Top Themes: {', '.join(analytics['top_philosophical_themes'][:3])}"
            return result
        
        else:
            return "❌ Unknown action. Use: 'contribute', 'query', 'analyze', or 'analytics'"
    
    def export_blockchain(self, format: str = "json") -> str:
        """Export blockchain in various formats"""
        if format == "json":
            return json.dumps(self.blockchain.chain, indent=2)
        elif format == "csv":
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Block', 'Timestamp', 'Insights', 'Claims', 'Confidence', 'Density', 'Hash'])
            
            for block in self.blockchain.chain:
                writer.writerow([
                    block['index'],
                    time.ctime(block['timestamp']),
                    len(block['data'].get('insights', [])),
                    len(block['data'].get('claims', [])),
                    block['truth_confidence'],
                    block['philosophical_density'],
                    block['hash'][:16]
                ])
            
            return output.getvalue()
        else:
            return "Unsupported format. Use 'json' or 'csv'"
