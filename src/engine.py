import json
import psutil
import os


class HubEngine:
    def __init__(self, data_path):
        self.data_path = data_path
        self.data = self._load_data()
        self.specs = self.get_specs()

    def _load_data(self):
        """Safely loads JSON with UTF-8 encoding."""
        if not os.path.exists(self.data_path):
            print(f"Error: {self.data_path} not found. Run the scraper first!")
            return []
        with open(self.data_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_specs(self):
        """Detects System RAM for compatibility checks."""
        virtual_mem = psutil.virtual_memory()
        return {
            "total_ram": round(virtual_mem.total / (1024 ** 3), 1),
            "available_ram": round(virtual_mem.available / (1024 ** 3), 1)
        }

    def parse_params(self, version_str):
        """
        Converts both parameter strings ('8b', '270m')
        AND file size strings ('1.3GB', '581MB') to a base float.
        """
        if not version_str: return 7.0
        v_clean = str(version_str).lower().strip()

        try:
            # --- Handle File Sizes (MB/GB) from the 'versions' list ---
            if 'gb' in v_clean:
                # If it's a file size, it's already basically the VRAM needed
                # We return it such that (params * 0.7) + 2 matches the size
                val = float(v_clean.replace('gb', ''))
                return (val - 2) / 0.7

            if 'mb' in v_clean:
                val = float(v_clean.replace('mb', '')) / 1024
                return (val - 2) / 0.7

            # --- Handle Parameter Counts (B/M) from primary_version ---
            if 'x' in v_clean:
                parts = v_clean.replace('b', '').split('x')
                return float(parts[0]) * float(parts[1])
            if 'm' in v_clean:
                return float(v_clean.replace('m', '')) / 1000
            if 'b' in v_clean:
                return float(v_clean.replace('b', ''))

            return 7.0
        except:
            return 7.0

    def recommend(self, task=None):
        recommendations = []

        tasks_to_check = []
        if isinstance(task, str):
            tasks_to_check = [task.lower()]
        elif isinstance(task, list):
            tasks_to_check = [str(t).lower() for t in task]

        for m in self.data:
            params = self.parse_params(m.get('primary_version', '7b'))
            vram_req = (params * 0.7) + 2

            if vram_req < (self.specs['total_ram'] * 0.6):
                status = "✅ Smooth"
            elif vram_req < self.specs['total_ram']:
                status = "⚠️ Slow (Swap)"
            else:
                status = "❌ Too Large"

            caps_raw = m.get('capabilities', [])
            caps = []
            for c in caps_raw:
                if isinstance(c, dict):
                    caps.append(str(next(iter(c.values()))).lower())
                else:
                    caps.append(str(c).lower())

            if tasks_to_check:
                if not any(t in caps for t in tasks_to_check):
                    continue

            recommendations.append({
                **m,
                "status": status,
                "vram_required": round(vram_req, 1),
                "capabilities": caps
            })
        return recommendations
