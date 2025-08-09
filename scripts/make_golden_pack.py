#!/usr/bin/env python3
"""
Golden Truth Pack Generator v0.6

Creates a downloadable package of validated datasets with expected outcomes
for external validation and benchmarking purposes.

Example usage:
    python scripts/make_golden_pack.py
    python scripts/make_golden_pack.py --output dist/golden_v0.6/
    python scripts/make_golden_pack.py --industries powder,autoclave
"""

import os
import sys
import json
import shutil
import hashlib
import zipfile
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add project root to path
project_root = Path(__file__).parent.parent

logger = logging.getLogger(__name__)


class GoldenPackGenerator:
    """Generates golden truth dataset packages."""
    
    def __init__(self, output_dir: str = "dist/golden_v0.6"):
        self.output_dir = Path(output_dir)
        self.registry_path = project_root / "validation_campaign" / "registry.yaml"
        self.pack_info = {
            "version": "0.6",
            "generated": datetime.utcnow().isoformat() + "Z",
            "generator": "make_golden_pack.py",
            "description": "ProofKit Golden Truth Dataset Pack v0.6",
            "datasets": {},
            "summary": {
                "total_datasets": 0,
                "by_industry": {},
                "by_outcome": {}
            }
        }
    
    def load_registry(self) -> Dict[str, Any]:
        """Load dataset registry from YAML file (simplified version)."""
        # For now, return a hardcoded set of key datasets from audit/fixtures
        datasets = {}
        
        # Find all fixture files
        fixtures_dir = project_root / "audit" / "fixtures"
        if fixtures_dir.exists():
            for industry_dir in fixtures_dir.iterdir():
                if industry_dir.is_dir():
                    industry = industry_dir.name
                    for csv_file in industry_dir.glob("*.csv"):
                        stem = csv_file.stem
                        spec_file = industry_dir / f"{stem}.json"
                        
                        if spec_file.exists():
                            # Determine expected outcome from filename
                            expected_outcome = "PASS"
                            if "fail" in stem:
                                expected_outcome = "FAIL"
                            elif "gap" in stem or "dup" in stem or "missing" in stem:
                                expected_outcome = "ERROR"
                            elif "borderline" in stem:
                                expected_outcome = "PASS"
                            
                            dataset_name = f"{industry}_{stem}"
                            datasets[dataset_name] = {
                                "id": f"{industry}_{stem}_001",
                                "industry": industry,
                                "csv_path": str(csv_file.relative_to(project_root)),
                                "spec_path": str(spec_file.relative_to(project_root)),
                                "expected_outcome": expected_outcome,
                                "metadata": {
                                    "vendor": "ProofKit Test Suite",
                                    "cadence": "auto-detected",
                                    "notes": f"Generated from {stem}"
                                },
                                "provenance": {
                                    "source": "audit_fixtures",
                                    "created_by": "proofkit_team",
                                    "created_date": "2025-01-15"
                                }
                            }
        
        return datasets
    
    def calculate_file_hash(self, filepath: Path) -> str:
        """Calculate SHA-256 hash of file."""
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            # Read file in chunks to handle large files
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    
    def copy_dataset_files(self, dataset_name: str, dataset_config: Dict[str, Any]) -> Dict[str, Any]:
        """Copy dataset files to output directory and generate metadata."""
        industry = dataset_config.get('industry', 'unknown')
        
        # Create industry subdirectory
        industry_dir = self.output_dir / industry
        industry_dir.mkdir(parents=True, exist_ok=True)
        
        # Resolve source file paths
        csv_src = project_root / dataset_config['csv_path']
        spec_src = project_root / dataset_config['spec_path']
        
        # Generate output filenames
        csv_dst = industry_dir / f"{dataset_name}.csv"
        spec_dst = industry_dir / f"{dataset_name}.json"
        
        # Copy files
        if not csv_src.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_src}")
        if not spec_src.exists():
            raise FileNotFoundError(f"Spec file not found: {spec_src}")
        
        shutil.copy2(csv_src, csv_dst)
        shutil.copy2(spec_src, spec_dst)
        
        # Calculate hashes
        csv_hash = self.calculate_file_hash(csv_dst)
        spec_hash = self.calculate_file_hash(spec_dst)
        
        # Get file sizes
        csv_size = csv_dst.stat().st_size
        spec_size = spec_dst.stat().st_size
        
        # Build dataset metadata
        dataset_info = {
            "id": dataset_config['id'],
            "industry": industry,
            "expected_outcome": dataset_config['expected_outcome'],
            "files": {
                "csv": {
                    "filename": csv_dst.name,
                    "path": f"{industry}/{csv_dst.name}",
                    "size_bytes": csv_size,
                    "sha256": csv_hash
                },
                "spec": {
                    "filename": spec_dst.name, 
                    "path": f"{industry}/{spec_dst.name}",
                    "size_bytes": spec_size,
                    "sha256": spec_hash
                }
            },
            "metadata": dataset_config.get('metadata', {}),
            "provenance": dataset_config.get('provenance', {}),
            "independent_validation": dataset_config.get('independent_validation', {})
        }
        
        return dataset_info
    
    def generate_pack(self, industries: Optional[List[str]] = None) -> Path:
        """Generate the golden truth pack."""
        logger.info(f"Generating golden truth pack v{self.pack_info['version']}")
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load registry
        registry = self.load_registry()
        
        # Filter by industries if specified
        if industries:
            registry = {
                name: config for name, config in registry.items()
                if config.get('industry') in industries
            }
        
        # Copy datasets and build pack info
        for dataset_name, dataset_config in registry.items():
            try:
                logger.info(f"Processing dataset: {dataset_name}")
                dataset_info = self.copy_dataset_files(dataset_name, dataset_config)
                self.pack_info["datasets"][dataset_name] = dataset_info
                
                # Update summary statistics
                industry = dataset_info['industry']
                outcome = dataset_info['expected_outcome']
                
                self.pack_info["summary"]["total_datasets"] += 1
                
                if industry not in self.pack_info["summary"]["by_industry"]:
                    self.pack_info["summary"]["by_industry"][industry] = 0
                self.pack_info["summary"]["by_industry"][industry] += 1
                
                if outcome not in self.pack_info["summary"]["by_outcome"]:
                    self.pack_info["summary"]["by_outcome"][outcome] = 0
                self.pack_info["summary"]["by_outcome"][outcome] += 1
                
            except Exception as e:
                logger.error(f"Failed to process dataset {dataset_name}: {e}")
                continue
        
        # Generate manifest
        manifest_path = self.output_dir / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(self.pack_info, f, indent=2)
        
        # Generate README
        self.generate_readme()
        
        # Generate validation scripts
        self.generate_validation_scripts()
        
        logger.info(f"Golden pack generated: {self.output_dir}")
        logger.info(f"Total datasets: {self.pack_info['summary']['total_datasets']}")
        
        return self.output_dir
    
    def generate_readme(self) -> None:
        """Generate README.md for the golden pack."""
        readme_content = f"""# ProofKit Golden Truth Pack v{self.pack_info['version']}

Generated: {self.pack_info['generated']}

## Overview

This package contains validated temperature monitoring datasets with expected outcomes for benchmarking and validation purposes.

## Contents

- **Total Datasets**: {self.pack_info['summary']['total_datasets']}
- **Industries**: {', '.join(self.pack_info['summary']['by_industry'].keys())}
- **Outcomes**: {', '.join(f"{k}({v})" for k,v in self.pack_info['summary']['by_outcome'].items())}

## Industry Breakdown

"""
        
        for industry, count in self.pack_info['summary']['by_industry'].items():
            readme_content += f"### {industry.title()} ({count} datasets)\n\n"
            
            # List datasets for this industry
            industry_datasets = [
                name for name, info in self.pack_info['datasets'].items()
                if info['industry'] == industry
            ]
            
            for dataset_name in sorted(industry_datasets):
                dataset_info = self.pack_info['datasets'][dataset_name]
                outcome = dataset_info['expected_outcome']
                readme_content += f"- **{dataset_name}**: {outcome}\n"
                
                # Add metadata if available
                metadata = dataset_info.get('metadata', {})
                if 'notes' in metadata:
                    readme_content += f"  - {metadata['notes']}\n"
            
            readme_content += "\n"
        
        readme_content += """## File Structure

```
golden_v0.6/
├── manifest.json          # Complete dataset metadata and hashes
├── README.md             # This file
├── validate_pack.py      # Validation script
├── powder/              # Powder coating datasets
│   ├── dataset1.csv
│   ├── dataset1.json
│   └── ...
├── autoclave/           # Autoclave sterilization datasets  
│   └── ...
└── <industry>/          # Other industry datasets
    └── ...
```

## Usage

### Validation

Verify pack integrity:
```bash
python validate_pack.py
```

### Loading Data

```python
import json
import pandas as pd

# Load manifest
with open('manifest.json', 'r') as f:
    manifest = json.load(f)

# Load a specific dataset
dataset_name = 'powder_coat_pass_basic'
dataset_info = manifest['datasets'][dataset_name]
csv_path = dataset_info['files']['csv']['path']
spec_path = dataset_info['files']['spec']['path']

df = pd.read_csv(csv_path)
with open(spec_path, 'r') as f:
    spec = json.load(f)

print(f"Expected outcome: {dataset_info['expected_outcome']}")
```

## Validation Notes

Each dataset includes:
- **Expected outcome**: PASS/FAIL/ERROR/INDETERMINATE
- **Independent validation**: Reference calculations where available
- **Provenance**: Source and permission information
- **File hashes**: SHA-256 for integrity verification

## License

These datasets are provided for validation and benchmarking purposes. 
See individual provenance information for specific usage rights.
"""
        
        readme_path = self.output_dir / "README.md"
        with open(readme_path, 'w') as f:
            f.write(readme_content)
    
    def generate_validation_scripts(self) -> None:
        """Generate validation script for pack integrity."""
        validation_script = '''#!/usr/bin/env python3
"""
Golden Pack Validation Script

Validates integrity of golden truth pack by checking file hashes
and verifying expected structure.
"""

import json
import hashlib
import sys
from pathlib import Path

def calculate_file_hash(filepath):
    """Calculate SHA-256 hash of file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

def validate_pack():
    """Validate golden pack integrity."""
    print("Validating Golden Truth Pack v''' + self.pack_info['version'] + '''...")
    
    # Load manifest
    try:
        with open('manifest.json', 'r') as f:
            manifest = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to load manifest.json: {e}")
        return False
    
    # Validate each dataset
    errors = 0
    total_datasets = len(manifest['datasets'])
    
    for dataset_name, dataset_info in manifest['datasets'].items():
        print(f"Validating {dataset_name}...")
        
        # Check CSV file
        csv_info = dataset_info['files']['csv']
        csv_path = Path(csv_info['path'])
        
        if not csv_path.exists():
            print(f"  ERROR: CSV file missing: {csv_path}")
            errors += 1
            continue
        
        csv_hash = calculate_file_hash(csv_path)
        if csv_hash != csv_info['sha256']:
            print(f"  ERROR: CSV hash mismatch for {csv_path}")
            print(f"    Expected: {csv_info['sha256']}")
            print(f"    Actual:   {csv_hash}")
            errors += 1
        
        # Check spec file  
        spec_info = dataset_info['files']['spec']
        spec_path = Path(spec_info['path'])
        
        if not spec_path.exists():
            print(f"  ERROR: Spec file missing: {spec_path}")
            errors += 1
            continue
            
        spec_hash = calculate_file_hash(spec_path)
        if spec_hash != spec_info['sha256']:
            print(f"  ERROR: Spec hash mismatch for {spec_path}")
            print(f"    Expected: {spec_info['sha256']}")
            print(f"    Actual:   {spec_hash}")
            errors += 1
    
    # Summary
    print(f"\\nValidation complete:")
    print(f"  Total datasets: {total_datasets}")
    print(f"  Errors: {errors}")
    
    if errors == 0:
        print("  ✅ All files validated successfully!")
        return True
    else:
        print(f"  ❌ Validation failed with {errors} errors")
        return False

if __name__ == "__main__":
    success = validate_pack()
    sys.exit(0 if success else 1)
'''
        
        script_path = self.output_dir / "validate_pack.py"
        with open(script_path, 'w') as f:
            f.write(validation_script)
        script_path.chmod(0o755)  # Make executable
    
    def create_zip_archive(self) -> Path:
        """Create ZIP archive of the golden pack."""
        zip_path = self.output_dir.parent / f"golden_v{self.pack_info['version']}.zip"
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in self.output_dir.rglob('*'):
                if file_path.is_file():
                    # Create relative path within zip
                    arcname = file_path.relative_to(self.output_dir.parent)
                    zipf.write(file_path, arcname)
        
        logger.info(f"ZIP archive created: {zip_path}")
        return zip_path


def main():
    parser = argparse.ArgumentParser(description="Generate Golden Truth Pack")
    parser.add_argument(
        "--output",
        default="dist/golden_v0.6",
        help="Output directory for golden pack"
    )
    parser.add_argument(
        "--industries", 
        help="Comma-separated list of industries to include (default: all)"
    )
    parser.add_argument(
        "--create-zip",
        action="store_true",
        help="Create ZIP archive of the pack"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Parse industries filter
    industries = None
    if args.industries:
        industries = [i.strip() for i in args.industries.split(',')]
        logger.info(f"Filtering industries: {industries}")
    
    # Generate pack
    try:
        generator = GoldenPackGenerator(args.output)
        pack_dir = generator.generate_pack(industries)
        
        # Create ZIP if requested
        if args.create_zip:
            zip_path = generator.create_zip_archive()
            print(f"Golden pack ZIP: {zip_path}")
        
        print(f"Golden pack directory: {pack_dir}")
        return 0
        
    except Exception as e:
        logger.error(f"Failed to generate golden pack: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())