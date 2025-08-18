#!/usr/bin/env python3
"""
Parallel Inference Runner for Hugging Face Datasets

This script runs inference on queries from Hugging Face datasets in parallel,
with automatic port management and organized output directory structure.

Usage:
    python inference_clean.py --dataset "luzimu/WebGen-Bench" --output-dir results
    python inference_clean.py --dataset "your/dataset" --column "question" --split "test" --output-dir results
    
Features:
- Load queries directly from Hugging Face datasets
- Parallel processing with configurable concurrency
- Automatic port management for Docker containers
- Organized output structure with caching support
- Progress tracking and summary reports
"""

import argparse
import asyncio
import json
import logging
import os
import socket
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datasets import load_dataset

# Import the predict function
sys.path.append(str(Path(__file__).parent))
from inference_with_docker import async_predict


class PortManager:
    """Manages port allocation for Docker containers"""
    
    def __init__(self, start_port: int = 6000, max_port: int = 7000):
        self.start_port = start_port
        self.max_port = max_port
        self.used_ports = set()
    
    def find_free_port(self) -> Optional[int]:
        """Find a free port in the specified range"""
        for port in range(self.start_port, self.max_port + 1):
            if port not in self.used_ports and self._is_port_free(port):
                self.used_ports.add(port)
                return port
        return None
    
    def release_port(self, port: int):
        """Release a port back to the available pool"""
        self.used_ports.discard(port)
    
    @staticmethod
    def _is_port_free(port: int) -> bool:
        """Check if a port is free to use"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', port))
                return result != 0
        except Exception:
            return False


class DatasetInferenceRunner:
    """Handles parallel inference on dataset queries"""
    
    def __init__(self, output_dir: str, settings_config: Dict[str, Any], 
                 max_workers: int = 4, port_start: int = 6000, port_max: int = 7000):
        self.output_dir = Path(output_dir)
        self.settings_config = settings_config
        self.max_workers = max_workers
        self.port_manager = PortManager(port_start, port_max)
        self.logger = self._setup_logger()
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _setup_logger(self) -> logging.Logger:
        """Set up logging configuration"""
        logger = logging.getLogger('DatasetInference')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            # Console handler
            console_handler = logging.StreamHandler()
            console_formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%H:%M:%S'
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
            
            # File handler
            log_file = self.output_dir / 'inference.log'
            file_handler = logging.FileHandler(log_file)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        
        return logger
    
    def load_dataset_queries(self, dataset_name: str, column: str = 'instruction', 
                           split: str = 'train', start_idx: int = 0, 
                           end_idx: Optional[int] = None) -> List[str]:
        """Load queries from Hugging Face dataset"""
        self.logger.info(f"Loading dataset: {dataset_name}")
        
        try:
            dataset = load_dataset(dataset_name)[split]
            
            if column not in dataset.column_names:
                available_columns = ', '.join(dataset.column_names)
                raise ValueError(f"Column '{column}' not found. Available columns: {available_columns}")
            
            queries = dataset[column]
            
            # Apply index slicing
            if end_idx is None:
                queries = queries[start_idx:]
            else:
                queries = queries[start_idx:end_idx]
            
            self.logger.info(f"Loaded {len(queries)} queries from {dataset_name}")
            return queries
            
        except Exception as e:
            self.logger.error(f"Failed to load dataset: {e}")
            raise
    
    async def process_query(self, query: str, query_id: str) -> Dict[str, Any]:
        """Process a single query"""
        start_time = time.time()
        
        # Check for cached results
        workspace_path = self.output_dir / query_id
        cache_file = workspace_path / ".ii_agent" / "current_state.json"
        
        if cache_file.exists():
            self.logger.info(f"✅ Using cached result for {query_id}")
            return {
                'query_id': query_id,
                'status': 'cached',
                'processing_time': 0
            }
        
        # Find free port
        port = self.port_manager.find_free_port()
        if port is None:
            self.logger.error(f"No free ports available for {query_id}")
            return {
                'query_id': query_id,
                'status': 'failed',
                'error': 'No free ports available',
                'processing_time': 0
            }
        
        try:
            # Create workspace
            workspace_path.mkdir(parents=True, exist_ok=True)
            ii_agent_dir = workspace_path / ".ii_agent"
            ii_agent_dir.mkdir(parents=True, exist_ok=True)
            
            session_id = f"{query_id}-{int(time.time())}"
            
            self.logger.info(f"Processing {query_id} on port {port}")
            
            # Run inference
            response = await async_predict(
                query=query,
                workspace_path=str(workspace_path),
                session_id=session_id,
                local_file_storage=str(ii_agent_dir),
                continue_from_state=False,
                setting_path=json.dumps(self.settings_config),
                port_mcp=port
            )
            
            # Save results
            results = {
                'query_id': query_id,
                'query': query,
                'response': response,
                'status': 'completed',
                'workspace_path': str(workspace_path),
                'port_used': port,
                'processing_time': time.time() - start_time
            }
            
            results_file = workspace_path / "results.json"
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"✅ Completed {query_id} in {results['processing_time']:.2f}s")
            return results
            
        except Exception as e:
            self.logger.error(f"❌ Error processing {query_id}: {e}")
            return {
                'query_id': query_id,
                'query': query,
                'status': 'failed',
                'error': str(e),
                'processing_time': time.time() - start_time
            }
        finally:
            self.port_manager.release_port(port)
    
    async def run_parallel_inference(self, queries: List[str]) -> List[Dict[str, Any]]:
        """Run inference on multiple queries in parallel"""
        # Create query tasks
        query_tasks = [(query, f"query_{i:04d}") for i, query in enumerate(queries)]
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_workers)
        
        async def process_with_limit(query: str, query_id: str):
            async with semaphore:
                return await self.process_query(query, query_id)
        
        self.logger.info(f"Starting parallel inference on {len(queries)} queries")
        self.logger.info(f"Max concurrent workers: {self.max_workers}")
        
        # Process all queries
        tasks = [process_with_limit(query, qid) for query, qid in query_tasks]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                query, query_id = query_tasks[i]
                processed_results.append({
                    'query_id': query_id,
                    'status': 'failed',
                    'error': str(result),
                    'processing_time': 0
                })
            elif result:  # Skip None results (cached)
                processed_results.append(result)
        
        return processed_results
    
    def generate_summary(self, results: List[Dict[str, Any]], total_queries: int) -> str:
        """Generate summary report"""
        completed = sum(1 for r in results if r.get('status') == 'completed')
        failed = sum(1 for r in results if r.get('status') == 'failed')
        cached = sum(1 for r in results if r.get('status') == 'cached')
        total_time = sum(r.get('processing_time', 0) for r in results)
        
        summary = f"""
╔══════════════════════════════════════════════════════╗
║          INFERENCE SUMMARY REPORT                     ║
╚══════════════════════════════════════════════════════╝

📊 Statistics:
  • Total Queries: {total_queries}
  • Completed: {completed}
  • Failed: {failed}
  • Cached: {cached}
  • Success Rate: {(completed/(completed+failed))*100 if (completed+failed) > 0 else 0:.1f}%
  
⏱️  Performance:
  • Total Processing Time: {total_time:.2f}s
  • Average Time per Query: {total_time/max(completed, 1):.2f}s
  
📁 Output Directory: {self.output_dir}
"""
        
        if failed > 0:
            summary += "\n❌ Failed Queries:\n"
            for r in results:
                if r.get('status') == 'failed':
                    summary += f"  • {r['query_id']}: {r.get('error', 'Unknown error')}\n"
        
        return summary


async def main():
    parser = argparse.ArgumentParser(
        description="Run parallel inference on Hugging Face dataset queries",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Dataset configuration
    parser.add_argument('--dataset', required=True, 
                       help='Hugging Face dataset name (e.g., "luzimu/WebGen-Bench")')
    parser.add_argument('--column', default='instruction',
                       help='Dataset column containing queries (default: instruction)')
    parser.add_argument('--split', default='train',
                       help='Dataset split to use (default: train)')
    parser.add_argument('--start-idx', type=int, default=0,
                       help='Starting index for queries (default: 0)')
    parser.add_argument('--end-idx', type=int, default=None,
                       help='Ending index for queries (default: all)')
    
    # Execution configuration
    parser.add_argument('--output-dir', required=True,
                       help='Output directory for results')
    parser.add_argument('--settings', default='workspace_predict/.ii_agent/settings.json',
                       help='Path to settings JSON file')
    parser.add_argument('--max-workers', type=int, default=4,
                       help='Maximum concurrent workers (default: 4)')
    
    # Port configuration
    parser.add_argument('--port-start', type=int, default=6000,
                       help='Starting port for Docker containers (default: 6000)')
    parser.add_argument('--port-max', type=int, default=7000,
                       help='Maximum port for Docker containers (default: 7000)')
    
    # Logging
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default='INFO', help='Logging level (default: INFO)')
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(level=getattr(logging, args.log_level))
    
    try:
        # Load settings
        with open(args.settings, 'r') as f:
            settings_config = json.load(f)
        
        # Initialize runner
        runner = DatasetInferenceRunner(
            output_dir=args.output_dir,
            settings_config=settings_config,
            max_workers=args.max_workers,
            port_start=args.port_start,
            port_max=args.port_max
        )
        
        # Load dataset queries
        queries = runner.load_dataset_queries(
            dataset_name=args.dataset,
            column=args.column,
            split=args.split,
            start_idx=args.start_idx,
            end_idx=args.end_idx
        )
        
        if not queries:
            print("No queries to process")
            return 1
        
        # Run inference
        start_time = time.time()
        results = await runner.run_parallel_inference(queries)
        total_time = time.time() - start_time
        
        # Save results
        results_file = Path(args.output_dir) / 'all_results.json'
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        # Generate and save summary
        summary = runner.generate_summary(results, len(queries))
        summary_file = Path(args.output_dir) / 'summary.txt'
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        print(summary)
        print(f"\n✅ Results saved to: {results_file}")
        print(f"📄 Summary saved to: {summary_file}")
        print(f"⏱️  Total execution time: {total_time:.2f}s")
        
        # Return exit code based on failures
        failed_count = sum(1 for r in results if r.get('status') == 'failed')
        return 1 if failed_count > 0 else 0
        
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)