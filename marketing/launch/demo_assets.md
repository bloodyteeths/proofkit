# Demo Assets Reference

## Screen Recording GIFs (to be created)

### 1. Powder Coating Demo
**File:** `/examples/powder_demo.gif`
**Script:**
1. Navigate to https://proofkit.net
2. Click "Powder Coating" industry
3. Upload `examples/powder_pass_fixed.csv`
4. Show specification with 180°C target
5. Submit and show PASS result
6. Download PDF certificate
7. Show QR code and verification hash

### 2. Autoclave F0 Demo
**File:** `/examples/autoclave_demo.gif`
**Script:**
1. Navigate to https://proofkit.net/industries/autoclave
2. Upload `examples/autoclave_sterilization_pass.csv`
3. Show F0 calculation parameters
4. Submit and show F0 value > 12
5. Download evidence bundle
6. Run verification script

## Recording Tools
- Use QuickTime or OBS for screen capture
- Convert to GIF with `ffmpeg -i demo.mov -vf "fps=10,scale=800:-1" -c:v gif demo.gif`
- Optimize with `gifsicle -O3 demo.gif -o demo_optimized.gif`
- Target size: <2MB per GIF