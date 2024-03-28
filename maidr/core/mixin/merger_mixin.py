class DictMergerMixin:
    @staticmethod
    def merge_dict(to_dict: dict, from_dict: dict) -> dict:
        for key, value in from_dict.items():
            if key in to_dict:
                if isinstance(to_dict[key], dict) and isinstance(value, dict):
                    # Recursively merge dictionaries
                    DictMergerMixin.merge_dict(to_dict[key], value)
                else:
                    # Update value if not both are dictionaries
                    to_dict[key] = value
            else:
                # Add new key-value pair
                to_dict[key] = value
        return to_dict
