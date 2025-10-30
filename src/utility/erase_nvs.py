"""
Andrea Favero 20251112

Self-learning clock project

Utility function to erase the NVS namespace 'storage' where
the correction factor gets stored.
This is only necessary for testing, to replicate a 'clean start'



MIT License

Copyright (c) 2025 Andrea Favero

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from esp32 import NVS

def clear_nvs(namespace=None):
    """Erase all keys in a specific NVS namespace (e.g., 'storage')"""
    
    if namespace is None:
        print("\n[DEBUG]   Necessary to specify a NVS namespace\n")
    
    if namespace is not None:
        try:
            nvs = NVS(namespace)

            # try to remove all stored keys (numbers 1–10 for example)
            # since NVS doesn't provide key enumeration in MicroPython.
            for key_id in range(1, 11):
                key = str(key_id)
                try:
                    nvs.erase_key(key)
                    print(f"[INFO]    Key '{key}' erased from NVS")
                except OSError as e:
                    # -4354 (ESP_ERR_NVS_NOT_FOUND) means no such key
                    if getattr(e, "errno", None) == -4354:
                        print(f"[DEBUG]   Key '{key}' not found, skipping")
                    else:
                        print(f"[ERROR]   Issue erasing key '{key}': {e}")

            nvs.commit()
            print("[INFO]    NVS cleanup completed successfully")

        except Exception as e:
            print(f"[ERROR]   Cannot open NVS namespace '{namespace}': {e}")


# run directly to erase the testing
if __name__ == "__main__":
    clear_nvs(namespace="storage")