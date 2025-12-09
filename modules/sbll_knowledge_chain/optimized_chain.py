"""
Optimized version of the SBLL blockchain implementation
"""

import hashlib
import time
import json
import os
import logging
from typing import Dict, List, Any, Optional
from enum import Enum
import numpy as np

from .chain import SBBLBlockchain

logger = logging.getLogger(__name__)

class OptimizedSBBLBlockchain(SBBLBlockchain):
    """Optimized version with performance improvements"""
    
    def __init__(self, cache_size: int = 100):
        super().__init__()
        self.block_cache = {}  # Cache for frequently accessed blocks
        self.cache_size = cache_size
        self.metrics_cache = {}  # Cache for calculated metrics
        self.hash_cache = {}  # Cache for content hashes
        
    def _calculate_block_hash(self, data: Dict, previous_hash: str, nonce: int = 0) -> str:
        """Optimized hash calculation with caching"""
        cache_key = f"{json.dumps(data, sort_keys=True)}{previous_hash}{nonce}"
        
        if cache_key in self.hash_cache:
            return self.hash_cache[cache_key]
        
        block_string = json.dumps(data, sort_keys=True) + previous_hash + str(nonce)
        block_hash = hashlib.sha3_256(block_string.encode()).hexdigest()
        
        # Cache the result
        if len(self.hash_cache) < 1000:  # Limit cache size
            self.hash_cache[cache_key] = block_hash
        
        return block_hash
    
    def get_block(self, index: int, use_cache: bool = True) -> Optional[Dict]:
        """Get block with optional caching"""
        if use_cache and index in self.block_cache:
            return self.block_cache[index]
        
        if 0 <= index < len(self.chain):
            block = self.chain[index]
            if use_cache:
                self._add_to_cache(index, block)
            return block
        
        return None
    
    def _add_to_cache(self, index: int, block: Dict):
        """Add block to cache with LRU eviction"""
        if index in self.block_cache:
            # Move to front (most recently used)
            del self.block_cache[index]
        
        self.block_cache[index] = block
        
        # Evict if cache is full
        if len(self.block_cache) > self.cache_size:
            # Remove oldest (first inserted)
            oldest_key = next(iter(self.block_cache))
            del self.block_cache[oldest_key]
    
    def batch_add_insights(self, insights: List[Dict]):
        """Batch add insights for better performance"""
        for insight in insights:
            self.add_philosophical_insight(insight)
    
    def get_chain_metrics(self, recalculate: bool = False) -> Dict:
        """Get chain metrics with caching"""
        if not recalculate and 'chain_metrics' in self.metrics_cache:
            return self.metrics_cache['chain_metrics']
        
        metrics = {
            'total_blocks': len(self.chain),
            'total_insights': sum(len(block['data'].get('insights', [])) for block in self.chain),
            'total_claims': sum(len(block['data'].get('claims', [])) for block in self.chain),
            'avg_confidence': np.mean([block['truth_confidence'] for block in self.chain]) if self.chain else 0,
            'avg_density': np.mean([block['philosophical_density'] for block in self.chain]) if self.chain else 0,
            'chain_integrity': self._calculate_chain_integrity()
        }
        
        self.metrics_cache['chain_metrics'] = metrics
        return metrics
    
    def _calculate_chain_integrity(self) -> float:
        """Calculate chain integrity score"""
        if len(self.chain) <= 1:
            return 1.0
        
        valid_links = 0
        for i in range(1, len(self.chain)):
            if self.chain[i]['previous_hash'] == self.chain[i-1]['hash']:
                valid_links += 1
        
        return valid_links / (len(self.chain) - 1)
    
    def save_chain_state_compressed(self, filename: str = "sbll_ledger_compressed.json"):
        """Save chain state with compression"""
        import gzip
        
        state = {
            'chain': self.chain,
            'pending_insights': self.pending_insights,
            'pending_claims': self.pending_claims,
            'difficulty': self.current_difficulty,
            'version': 'SBLL-2.0',
            'saved_at': time.time()
        }
        
        try:
            # Save regular JSON
            with open(filename, 'w') as f:
                json.dump(state, f, separators=(',', ':'))  # Minified
            
            # Also save compressed version
            compressed_filename = filename.replace('.json', '.json.gz')
            with gzip.open(compressed_filename, 'wt', encoding='utf-8') as f:
                json.dump(state, f)
            
            logger.info(f"Saved compressed ledger to {compressed_filename}")
            
        except Exception as e:
            logger.error(f"Failed to save compressed ledger: {e}")
            # Fall back to regular save
            super().save_chain_state(filename)
