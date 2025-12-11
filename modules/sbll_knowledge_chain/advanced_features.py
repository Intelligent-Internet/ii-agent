"""
Advanced features for the SBLL Philosophical Blockchain
Building on the existing implementation
"""

import numpy as np
from typing import Dict, List, Any, Tuple
from enum import Enum

class AdvancedPhilosophicalMetrics:
    """Advanced metrics and analytics for philosophical content"""
    
    @staticmethod
    def calculate_semantic_density(content: str) -> float:
        """Calculate semantic density of philosophical content"""
        words = content.split()
        philosophical_terms = {
            'consciousness', 'reality', 'truth', 'meaning', 'ethics',
            'cosmic', 'optimization', 'constraint', 'emergence', 'verification'
        }
        
        if not words:
            return 0.0
            
        philosophical_count = sum(1 for word in words if word.lower() in philosophical_terms)
        return philosophical_count / len(words)
    
    @staticmethod
    def calculate_inference_complexity(content: str) -> int:
        """Calculate inference complexity based on logical connectors"""
        connectors = {
            'because': 2, 'therefore': 2, 'thus': 2, 'hence': 2,
            'if': 1, 'then': 1, 'implies': 2, 'requires': 1,
            'emerges': 3, 'transcends': 3, 'manifests': 2
        }
        
        complexity = 0
        for connector, weight in connectors.items():
            if connector in content.lower():
                complexity += weight
        
        return complexity

class CrossTraditionSynthesizer:
    """Synthesize insights across philosophical traditions"""
    
    @staticmethod
    def synthesize_insights(insights: List[Dict]) -> Dict:
        """Synthesize multiple insights into unified understanding"""
        if not insights:
            return {'synthesis': 'No insights to synthesize', 'coherence': 0.0}
        
        # Group by tradition
        by_tradition = {}
        for insight in insights:
            trad = insight.get('tradition', 'UNIVERSAL')
            if trad not in by_tradition:
                by_tradition[trad] = []
            by_tradition[trad].append(insight)
        
        # Find common themes
        all_contents = [insight['content'] for insight in insights]
        common_words = CrossTraditionSynthesizer._find_common_words(all_contents)
        
        # Calculate cross-traditional coherence
        coherence = CrossTraditionSynthesizer._calculate_coherence(by_tradition)
        
        # Generate synthesis
        synthesis = f"Cross-traditional synthesis ({len(by_tradition)} traditions):\n"
        synthesis += f"Common themes: {', '.join(common_words[:3])}\n"
        
        for tradition, trad_insights in by_tradition.items():
            synthesis += f"\n• {tradition}: {len(trad_insights)} insights"
            if trad_insights:
                avg_confidence = sum(i.get('truth_confidence', 0) for i in trad_insights) / len(trad_insights)
                synthesis += f" (avg confidence: {avg_confidence:.0f})"
        
        return {
            'synthesis': synthesis,
            'coherence': coherence,
            'traditions_count': len(by_tradition),
            'total_insights': len(insights),
            'common_themes': common_words[:5]
        }
    
    @staticmethod
    def _find_common_words(contents: List[str], top_n: int = 10) -> List[str]:
        """Find most common words across multiple contents"""
        from collections import Counter
        
        # Common philosophical words to ignore
        stop_words = {'the', 'and', 'is', 'in', 'of', 'to', 'a', 'that', 'it', 'as'}
        
        all_words = []
        for content in contents:
            words = [word.lower().strip('.,!?;:\"\'') for word in content.split() if len(word) > 4 and word.lower() not in stop_words]
            all_words.extend(words)
        
        word_counts = Counter(all_words)
        return [word for word, _ in word_counts.most_common(top_n)]
    
    @staticmethod
    def _calculate_coherence(by_tradition: Dict) -> float:
        """Calculate coherence across traditions"""
        if len(by_tradition) < 2:
            return 1.0  # Single tradition is perfectly coherent with itself
        
        # Compare average confidence across traditions
        avg_confidences = []
        for trad_insights in by_tradition.values():
            avg_conf = sum(i.get('truth_confidence', 0) for i in trad_insights) / len(trad_insights)
            avg_confidences.append(avg_conf)
        
        # Calculate variance (lower variance = higher coherence)
        variance = np.var(avg_confidences) if avg_confidences else 0
        max_variance = 10000  # Arbitrary scaling
        coherence = 1.0 - min(1.0, variance / max_variance)
        
        return coherence

class BlockchainVisualizer:
    """Visualize and analyze the blockchain"""
    
    @staticmethod
    def generate_blockchain_report(chain: List[Dict]) -> Dict:
        """Generate comprehensive blockchain report"""
        if not chain:
            return {'error': 'Empty chain'}
        
        total_blocks = len(chain)
        total_insights = sum(len(block['data'].get('insights', [])) for block in chain)
        total_claims = sum(len(block['data'].get('claims', [])) for block in chain)
        
        # Calculate metrics over time
        confidences = [block['truth_confidence'] for block in chain]
        densities = [block['philosophical_density'] for block in chain]
        
        # Find patterns
        avg_confidence = np.mean(confidences)
        avg_density = np.mean(densities)
        
        # Calculate chain growth
        if len(chain) > 1:
            time_span = chain[-1]['timestamp'] - chain[0]['timestamp']
            blocks_per_day = (len(chain) - 1) / (time_span / 86400) if time_span > 0 else 0
        else:
            blocks_per_day = 0
        
        return {
            'total_blocks': total_blocks,
            'total_insights': total_insights,
            'total_claims': total_claims,
            'avg_confidence': avg_confidence,
            'avg_density': avg_density,
            'blocks_per_day': blocks_per_day,
            'chain_health': BlockchainVisualizer._calculate_chain_health(chain),
            'most_prolific_tradition': BlockchainVisualizer._find_most_prolific_tradition(chain),
            'top_philosophical_themes': BlockchainVisualizer._extract_themes(chain)
        }
    
    @staticmethod
    def _calculate_chain_health(chain: List[Dict]) -> float:
        """Calculate overall blockchain health"""
        if len(chain) < 2:
            return 1.0
        
        # Factors: consistency, growth, content quality
        consistency_score = BlockchainVisualizer._calculate_consistency(chain)
        growth_score = min(1.0, len(chain) / 10)  # Normalize to 10 blocks
        quality_score = np.mean([block['truth_confidence'] for block in chain]) / 255
        
        return (consistency_score + growth_score + quality_score) / 3
    
    @staticmethod
    def _calculate_consistency(chain: List[Dict]) -> float:
        """Calculate consistency across blocks"""
        if len(chain) < 2:
            return 1.0
        
        confidences = [block['truth_confidence'] for block in chain]
        variance = np.var(confidences)
        
        # Lower variance = higher consistency
        max_variance = 1000
        consistency = 1.0 - min(1.0, variance / max_variance)
        
        return consistency
    
    @staticmethod
    def _find_most_prolific_tradition(chain: List[Dict]) -> str:
        """Find which tradition contributes most content"""
        tradition_counts = {}
        
        for block in chain:
            for insight in block['data'].get('insights', []):
                trad = insight.get('tradition', 'UNKNOWN')
                tradition_counts[trad] = tradition_counts.get(trad, 0) + 1
        
        if not tradition_counts:
            return 'NONE'
        
        return max(tradition_counts.items(), key=lambda x: x[1])[0]
    
    @staticmethod
    def _extract_themes(chain: List[Dict], top_n: int = 5) -> List[str]:
        """Extract top philosophical themes from blockchain"""
        from collections import Counter
        
        all_content = []
        for block in chain:
            for insight in block['data'].get('insights', []):
                all_content.append(insight['content'])
            for claim in block['data'].get('claims', []):
                all_content.append(claim['content'])
        
        # Simple word frequency analysis
        philosophical_terms = {
            'consciousness', 'reality', 'truth', 'meaning', 'ethics',
            'cosmic', 'optimization', 'constraint', 'emergence', 'verification',
            'knowledge', 'wisdom', 'understanding', 'existence', 'being',
            'evolution', 'complexity', 'system', 'network', 'relation'
        }
        
        word_counts = Counter()
        for content in all_content:
            words = content.lower().split()
            for word in words:
                if word in philosophical_terms:
                    word_counts[word] += 1
        
        return [word for word, _ in word_counts.most_common(top_n)]

# Enhanced KnowledgeChainTool with advanced features
class EnhancedKnowledgeChainTool:
    """Enhanced version with advanced analytics"""
    
    def __init__(self):
        from .tool_wrapper import KnowledgeChainTool
        self.base_tool = KnowledgeChainTool()
        self.metrics = AdvancedPhilosophicalMetrics()
        self.synthesizer = CrossTraditionSynthesizer()
        self.visualizer = BlockchainVisualizer()
    
    def analyze_content(self, content: str) -> Dict:
        """Advanced analysis of philosophical content"""
        return {
            'semantic_density': self.metrics.calculate_semantic_density(content),
            'inference_complexity': self.metrics.calculate_inference_complexity(content),
            'estimated_confidence': self._estimate_confidence(content),
            'tradition_suggestions': self._suggest_tradition(content)
        }
    
    def synthesize_blockchain_wisdom(self, topic: str) -> Dict:
        """Synthesize all wisdom on a topic from blockchain"""
        # Query blockchain for topic
        results = self.base_tool.oracle.seek_wisdom(topic, min_confidence=100)
        
        if results['total_found'] == 0:
            return {'synthesis': f"No wisdom found on '{topic}'", 'insights': []}
        
        # Get all insights
        all_insights = []
        for block in self.base_tool.blockchain.chain:
            for insight in block['data'].get('insights', []):
                if topic.lower() in insight['content'].lower():
                    all_insights.append(insight)
        
        # Synthesize
        synthesis = self.synthesizer.synthesize_insights(all_insights)
        synthesis['topic'] = topic
        synthesis['source'] = 'SBLL Blockchain'
        
        return synthesis
    
    def get_blockchain_analytics(self) -> Dict:
        """Get comprehensive blockchain analytics"""
        return self.visualizer.generate_blockchain_report(self.base_tool.blockchain.chain)
    
    def _estimate_confidence(self, content: str) -> int:
        """Estimate truth confidence based on content analysis"""
        base_confidence = 180
        
        # Boosters
        if any(word in content.lower() for word in ['verified', 'evidence', 'proof', 'demonstrated']):
            base_confidence += 20
        
        if any(word in content.lower() for word in ['universal', 'fundamental', 'necessary', 'essential']):
            base_confidence += 15
        
        # Penalties
        if any(word in content.lower() for word in ['maybe', 'possibly', 'perhaps', 'might']):
            base_confidence -= 10
        
        return min(255, max(100, base_confidence))
    
    def _suggest_tradition(self, content: str) -> List[str]:
        """Suggest philosophical traditions based on content"""
        tradition_keywords = {
            'WESTERN_ANALYTIC': ['logic', 'analysis', 'empirical', 'verification', 'computation'],
            'EASTERN_BUDDHIST': ['impermanence', 'emptiness', 'mindfulness', 'suffering', 'nirvana'],
            'EASTERN_TAOIST': ['flow', 'harmony', 'natural', 'balance', 'wu wei'],
            'MODERN_SCIENTIFIC': ['experiment', 'data', 'theory', 'evidence', 'hypothesis']
        }
        
        suggestions = []
        content_lower = content.lower()
        
        for tradition, keywords in tradition_keywords.items():
            matches = sum(1 for keyword in keywords if keyword in content_lower)
            if matches >= 2:  # At least 2 keywords match
                suggestions.append(tradition)
        
        return suggestions if suggestions else ['WESTERN_ANALYTIC']  # Default

# Integration helper to enhance existing tool (returns a subclass)
def enhance_existing_tool():
    """Return an EnhancedTool subclass of KnowledgeChainTool"""
    from .tool_wrapper import KnowledgeChainTool as OriginalTool

    class EnhancedTool(OriginalTool):
        def __init__(self):
            super().__init__()
            self.enhanced_features = EnhancedKnowledgeChainTool()
        
        def advanced_query(self, topic: str) -> str:
            """Enhanced query with synthesis and analytics"""
            synthesis = self.enhanced_features.synthesize_blockchain_wisdom(topic)
            
            if synthesis.get('total_insights', 0):
                result = f"🔮 ADVANCED SYNTHESIS ON: {topic}\n"
                result += f"Found {synthesis['total_insights']} insights across {synthesis['traditions_count']} traditions\n"
                result += f"Cross-traditional coherence: {synthesis['coherence']:.1%}\n\n"
                result += synthesis['synthesis']
                return result
            else:
                return f"No synthesized wisdom found on '{topic}'"
        
        def get_analytics(self) -> str:
            """Get blockchain analytics"""
            analytics = self.enhanced_features.get_blockchain_analytics()
            
            result = "📊 BLOCKCHAIN ANALYTICS\n"
            result += f"• Total Blocks: {analytics['total_blocks']}\n"
            result += f"• Total Insights: {analytics['total_insights']}\n"
            result += f"• Average Confidence: {analytics['avg_confidence']:.0f}/255\n"
            result += f"• Chain Health: {analytics['chain_health']:.1%}\n"
            result += f"• Most Prolific Tradition: {analytics['most_prolific_tradition']}\n"
            result += f"• Top Themes: {', '.join(analytics['top_philosophical_themes'])}\n"
            
            return result
    
    return EnhancedTool
