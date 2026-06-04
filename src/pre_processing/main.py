import os
import json
import glob
from pathlib import Path
from .strategies.charaka import CharakaCleaner
from .strategies.susruta import SusrutaCleaner
from .strategies.astanga import AshtangaCleaner
from .strategies.markdown_base import MarkdownCleaner
from .integrity import IntegrityMonitor

import sys

def main():
    print("Main function started...")
    sys.stdout.flush()
    books_root = "books"
    output_root = "processed-books"
    
    try:
        charaka_cleaner = CharakaCleaner()
        susruta_cleaner = SusrutaCleaner()
        astanga_cleaner = AshtangaCleaner()
        generic_md_cleaner = MarkdownCleaner()
        monitor = IntegrityMonitor()
        
        report = []

        # Process Charaka (JSON Files)
        charaka_src = os.path.join(books_root, "charak_samhita")
        charaka_out = os.path.join(output_root, "charak_samhita")
        os.makedirs(charaka_out, exist_ok=True)
        
        print(f"Processing Charaka Samhita from {charaka_src}...")
        sys.stdout.flush()
        json_files = glob.glob(os.path.join(charaka_src, "*.json"))
        print(f"Found {len(json_files)} Charaka JSON files.")
        sys.stdout.flush()
        
        charaka_blacklist = {
            "About the Project.json",
            "Contributors.json",
            "Donate.json",
            "Governance.json",
            "Guidelines for writing.json",
            "Help.json",
            "Disclaimer.json",
            "Main Page.json",
            "Preface- Charak Samhita New Edition.json",
            "Referencing guidelines.json",
            "Technical Support.json",
            "Yogesh Deole.json",
            "Main_Page.json"
        }
        
        for json_file in json_files:
            filename = os.path.basename(json_file)
            # Robust check: normalize underscores to spaces for blacklist comparison
            normalized_filename = filename.replace('_', ' ')
            if (filename in charaka_blacklist or 
                normalized_filename in charaka_blacklist or 
                filename.startswith("Special:")):
                continue

            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            raw_text = data.get("text", "")
            processed_data = charaka_cleaner.process_json(data)
            proc_text = processed_data.get("text", "")
            
            stats = monitor.measure_loss(raw_text, proc_text)
            deva_warning = monitor.check_devanagari_loss(raw_text, proc_text)
            
            report.append({
                "file": filename,
                "treatise": "Charaka",
                **stats,
                "deva_warning": deva_warning
            })
            
            with open(os.path.join(charaka_out, filename), 'w', encoding='utf-8') as f:
                json.dump(processed_data, f, indent=2, ensure_ascii=False)

        # Process Susruta and Astanga (Markdown Files)
        treatises = [
            ("shusrut_samhita", "Shusrut_Samhita.md", susruta_cleaner),
            ("astanga_hridaya", "astanga-hridaya.md", astanga_cleaner)
        ]
        
        for folder, filename, cleaner in treatises:
            print(f"Processing {folder}...")
            sys.stdout.flush()
            src_path = os.path.join(books_root, folder, filename)
            out_dir = os.path.join(output_root, folder)
            os.makedirs(out_dir, exist_ok=True)
            
            if not os.path.exists(src_path):
                print(f"Warning: {src_path} not found.")
                sys.stdout.flush()
                continue
                
            with open(src_path, 'r', encoding='utf-8') as f:
                raw_text = f.read()
                
            proc_text = cleaner.clean(raw_text)
            
            # Monitor Integrity
            stats = monitor.measure_loss(raw_text, proc_text)
            deva_warning = monitor.check_devanagari_loss(raw_text, proc_text)
            
            report.append({
                "file": filename,
                "treatise": folder,
                **stats,
                "deva_warning": deva_warning
            })
            
            with open(os.path.join(out_dir, filename), 'w', encoding='utf-8') as f:
                f.write(proc_text)

        # Generate Final Report
        generate_markdown_report(report)
        print(f"\nProcessing complete! Report generated at processing_report.md")
        sys.stdout.flush()

    except Exception as e:
        print(f"An error occurred during processing: {e}")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()

def generate_markdown_report(report):
    with open("processing_report.md", "w", encoding="utf-8") as f:
        f.write("# Data Pre-processing Integrity Report\n\n")
        f.write("This report summarizes the cleaning process and measures information retention using TF-IDF analysis.\n\n")
        f.write("| Treatise | File | Retention Score (TF-IDF) | Loss % | Devanagari Warning |\n")
        f.write("|----------|------|-------------------------|--------|--------------------|\n")
        for entry in report:
            warning = "⚠️ **YES**" if entry["deva_warning"] else "OK"
            # Highlight scores below 0.9 as potential issues
            score_str = f"**{entry['retention_score']}**" if entry["retention_score"] < 0.9 else str(entry["retention_score"])
            f.write(f"| {entry['treatise']} | {entry['file']} | {score_str} | {entry['loss_percentage']}% | {warning} |\n")

if __name__ == "__main__":
    main()
