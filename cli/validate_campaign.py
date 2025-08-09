#!/usr/bin/env python3
"""
Validation Campaign Runner

Runs full pipeline (normalize → decide → render → bundle) for each registry item.
Saves outputs and compares against expected outcomes, building confusion matrix.

Example usage:
    python cli/validate_campaign.py
    python cli/validate_campaign.py --registry-path validation_campaign/registry.yaml
    python cli/validate_campaign.py --output-dir validation_outputs/
"""

import os
import sys
import yaml
import logging
import argparse
import pandas as pd
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.normalize import load_csv_with_metadata, normalize_temperature_data
from core.decide import make_decision  
from core.models import SpecV1, DecisionResult
from core.plot import generate_proof_plot
from core.render_pdf import generate_proof_pdf
from core.pack import create_evidence_bundle

logger = logging.getLogger(__name__)


class CampaignRunner:
    """Runs full validation campaign against registry datasets."""
    
    def __init__(self, registry_path: str, output_dir: str):
        self.registry_path = Path(registry_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        with open(self.registry_path, 'r') as f:
            self.registry = yaml.safe_load(f)
            
        self.results = []
        
    def run_single_case(self, dataset_id: str, dataset_config: Dict[str, Any]) -> Dict[str, Any]:
        """Run full pipeline for single registry item."""
        logger.info(f"Processing dataset: {dataset_id}")
        
        # Resolve file paths relative to project root
        csv_path = project_root / dataset_config['csv_path']
        spec_path = project_root / dataset_config['spec_path']
        
        case_output_dir = self.output_dir / dataset_id
        case_output_dir.mkdir(parents=True, exist_ok=True)
        
        result = {
            'dataset_id': dataset_id,
            'expected_outcome': dataset_config['expected_outcome'],
            'industry': dataset_config['industry'],
            'status': None,
            'actual_outcome': None,
            'error': None,
            'outputs': {}
        }
        
        try:
            # Load inputs
            with open(spec_path, 'r') as f:
                spec_data = json.load(f)
            spec = SpecV1(**spec_data)
            
            # Step 1: Load and Normalize
            logger.info(f"  Loading and normalizing CSV data from {csv_path}")
            df, metadata = load_csv_with_metadata(str(csv_path))
            normalized_df = normalize_temperature_data(df, industry=spec.industry)
            normalized_path = case_output_dir / "normalized.csv"
            normalized_df.to_csv(normalized_path, index=False)
            result['outputs']['normalized_csv'] = str(normalized_path)
            
            # Step 2: Decide
            logger.info(f"  Making decision")
            decision = make_decision(normalized_df, spec)
            decision_path = case_output_dir / "decision.json"
            with open(decision_path, 'w') as f:
                json.dump(decision.model_dump(), f, indent=2, default=str)
            result['outputs']['decision_json'] = str(decision_path)
            
            # Step 3: Extract metrics
            metrics = {
                'pass': decision.pass_,
                'status': 'PASS' if decision.pass_ else 'FAIL',
                'actual_hold_time_s': getattr(decision, 'actual_hold_time_s', None),
                'target_temp_C': getattr(decision, 'target_temp_C', None),
                'conservative_threshold': getattr(decision, 'conservative_threshold', None),
                'ramp_rate_C_per_min': getattr(decision, 'ramp_rate_C_per_min', None),
                'time_to_threshold_s': getattr(decision, 'time_to_threshold_s', None)
            }
            metrics_path = case_output_dir / "metrics.json"
            with open(metrics_path, 'w') as f:
                json.dump(metrics, f, indent=2)
            result['outputs']['metrics_json'] = str(metrics_path)
            
            # Step 4: Plot
            logger.info(f"  Creating temperature plot")
            plot_path = case_output_dir / "plot.png"
            generate_proof_plot(normalized_df, spec, decision, str(plot_path))
            result['outputs']['plot_png'] = str(plot_path)
            
            # Step 5: PDF
            logger.info(f"  Rendering PDF proof")
            pdf_path = case_output_dir / "proof.pdf"
            generate_proof_pdf(spec, decision, str(plot_path), output_path=str(pdf_path))
            result['outputs']['proof_pdf'] = str(pdf_path)
            
            # Step 6: Bundle
            logger.info(f"  Creating evidence bundle")
            bundle_path = case_output_dir / "evidence.zip"
            create_evidence_bundle(
                raw_csv_path=str(csv_path),
                spec_json_path=str(spec_path), 
                normalized_csv_path=str(normalized_path),
                decision_json_path=str(decision_path),
                proof_pdf_path=str(pdf_path),
                plot_png_path=str(plot_path),
                output_path=str(bundle_path),
                job_id=decision.job_id
            )
            result['outputs']['evidence_zip'] = str(bundle_path)
            
            # Determine actual outcome
            if decision.pass_:
                result['actual_outcome'] = 'PASS'
            else:
                result['actual_outcome'] = 'FAIL'
            result['status'] = 'SUCCESS'
            
        except Exception as e:
            logger.error(f"  Error processing {dataset_id}: {e}")
            result['status'] = 'ERROR'
            result['error'] = str(e)
            result['actual_outcome'] = 'ERROR'
            
        return result
        
    def run_campaign(self) -> List[Dict[str, Any]]:
        """Run full validation campaign."""
        logger.info(f"Starting validation campaign with {len(self.registry['datasets'])} datasets")
        
        for dataset_id, dataset_config in self.registry['datasets'].items():
            result = self.run_single_case(dataset_id, dataset_config)
            self.results.append(result)
            
        return self.results
        
    def build_confusion_matrix(self) -> Dict[str, Any]:
        """Build confusion matrix from results."""
        matrix = {}
        
        # Initialize matrix
        outcomes = ['PASS', 'FAIL', 'ERROR', 'INDETERMINATE']
        for expected in outcomes:
            matrix[expected] = {}
            for actual in outcomes:
                matrix[expected][actual] = 0
                
        # Populate matrix
        for result in self.results:
            expected = result['expected_outcome']
            actual = result['actual_outcome'] or 'ERROR'
            if expected in matrix and actual in matrix[expected]:
                matrix[expected][actual] += 1
                
        # Calculate summary stats
        total_cases = len(self.results)
        correct_predictions = sum(
            matrix[outcome][outcome] for outcome in outcomes
            if outcome in matrix and outcome in matrix[outcome]
        )
        accuracy = correct_predictions / total_cases if total_cases > 0 else 0
        
        return {
            'confusion_matrix': matrix,
            'total_cases': total_cases,
            'correct_predictions': correct_predictions,
            'accuracy': accuracy,
            'timestamp': datetime.now().isoformat()
        }
        
    def save_results(self) -> None:
        """Save campaign results and confusion matrix."""
        # Save detailed results
        results_path = self.output_dir / "campaign_results.json"
        with open(results_path, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
            
        # Save confusion matrix
        confusion_matrix = self.build_confusion_matrix()
        matrix_path = self.output_dir / "confusion_matrix.json"
        with open(matrix_path, 'w') as f:
            json.dump(confusion_matrix, f, indent=2)
            
        logger.info(f"Results saved to {results_path}")
        logger.info(f"Confusion matrix saved to {matrix_path}")
        logger.info(f"Accuracy: {confusion_matrix['accuracy']:.2%}")


def main():
    parser = argparse.ArgumentParser(description="Run validation campaign")
    parser.add_argument(
        "--registry-path", 
        default="validation_campaign/registry.yaml",
        help="Path to registry YAML file"
    )
    parser.add_argument(
        "--output-dir",
        default="validation_outputs",
        help="Output directory for results"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    runner = CampaignRunner(args.registry_path, args.output_dir)
    runner.run_campaign()
    runner.save_results()


if __name__ == "__main__":
    main()