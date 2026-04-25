import logging
from abc import ABC
from collections.abc import Iterable
from collections.abc import Mapping
from typing import Any
from typing import Dict
from typing import get_origin
from typing import List
from typing import Optional

from config_resolver.models import ConflictRecord
from config_resolver.profiles.base import BaseProfile
from config_resolver.profiles.exceptions import ProfileUnavailableError
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class BaseConfig(BaseSettings, ABC):
    """Base class for application settings, populated by env vars +
    configurable Profile sources.

    Extend this with concrete fields.
    """

    profiles: list[BaseProfile] = []
    sensitive_fields: list[str] = ["password", "token", "api_key"]
    _conflicts: list[ConflictRecord] = []

    @model_validator(mode="after")
    def _validate_and_resolve(self) -> "BaseConfig":
        """Pydantic model validator that triggers config resolution after model
        initialization. This ensures all fields are resolved and conflicts are
        detected automatically.

        Returns:
            The resolved BaseConfig instance.
        """
        self._resolve()
        return self

    def _resolve(self) -> None:
        """Main resolution method that orchestrates the config merging process.

        Fetches all profiles, then iterates through each field to
        resolve values from environment and profile sources. Detects and
        records any conflicts.
        """
        self._conflicts = []
        fetched_profiles = self._fetch_profiles()

        logger.info(
            "Starting config resolution with %d fetched profiles", len(fetched_profiles)
        )

        for field_name in self.__class__.model_fields.keys():
            if field_name in ["profiles", "_conflicts"]:
                continue

            env_value = getattr(self, field_name)
            self._resolve_field(
                field_name=field_name,
                current_value=env_value,
                fetched_profiles=fetched_profiles,
                key_path=field_name,
            )

        logger.info(
            "Config resolution complete. Detected %d conflicts", len(self._conflicts)
        )

    def _fetch_profiles(self) -> list[BaseProfile]:
        """Fetch all configured profiles and return the successfully fetched
        ones.

        Iterates through all profiles, attempts to fetch each one, and logs
        warnings for any profiles that fail to fetch.

        Returns:
            List of profiles that were successfully fetched (have last_updated_at set).
        """
        for profile in self.profiles:
            profile_name = profile.__class__.__name__
            try:
                profile.fetch()
                logger.info("Successfully fetched profile: %s", profile_name)
            except ProfileUnavailableError as e:
                logger.warning(
                    "Profile '%s' is unavailable and will be skipped: %s",
                    profile_name,
                    str(e),
                )
                continue

        return [p for p in self.profiles if p.last_updated_at is not None]

    def _get_field_type(self, field_name: str) -> Any:
        """Get the type annotation for a field by its name.

        Args:
            field_name: The name of the field to get the type for.

        Returns:
            The type annotation of the field, or None if not found.
        """
        field_info = self.__class__.model_fields.get(field_name)
        if field_info is not None:
            return field_info.annotation
        return None

    def _is_nested_type(self, field_type: Any) -> bool:
        """Determine if a field type is a nested type that requires recursive
        resolution.

        Nested types include:
        - Dictionaries (dict, Mapping)
        - Lists, sets, tuples and other iterables (excluding str and bytes)
        - Pydantic BaseModel subclasses

        Args:
            field_type: The type annotation to check.

        Returns:
            True if the type is a nested type, False otherwise.
        """
        if field_type is None:
            return False

        origin = get_origin(field_type)

        # Check generic types (e.g., Dict[str, Any], List[int])
        if origin is not None:
            if isinstance(origin, type) and issubclass(origin, Mapping):
                return True
            if (
                isinstance(origin, type)
                and issubclass(origin, Iterable)
                and origin not in (str, bytes)
            ):
                return True

        # Check concrete types
        if isinstance(field_type, type):
            if issubclass(field_type, BaseModel):
                return True
            if issubclass(field_type, Mapping):
                return True
            if issubclass(field_type, Iterable) and field_type not in (str, bytes):
                return True

        return False

    def _is_pydantic_model(self, value: Any) -> bool:
        """Check if a value is a Pydantic BaseModel instance.

        Args:
            value: The value to check.

        Returns:
            True if the value is a BaseModel instance, False otherwise.
        """
        return isinstance(value, BaseModel)

    def _is_dict_like(self, value: Any) -> bool:
        """Check if a value is a dictionary or mapping type.

        Args:
            value: The value to check.

        Returns:
            True if the value is a Mapping, False otherwise.
        """
        return isinstance(value, Mapping)

    def _is_iterable_collection(self, value: Any) -> bool:
        """Check if a value is an iterable collection (list, tuple, set, etc.).

        Excludes strings, bytes, and mappings from being considered iterable collections.

        Args:
            value: The value to check.

        Returns:
            True if the value is an iterable collection, False otherwise.
        """
        return isinstance(value, Iterable) and not isinstance(
            value, (str, bytes, Mapping)
        )

    def _collect_profile_sources(
        self, field_name: str, fetched_profiles: list[BaseProfile]
    ) -> dict[str, Any]:
        """Collect all profile sources that have a non-None value for a given
        field.

        Args:
            field_name: The name of the field to collect values for.
            fetched_profiles: List of successfully fetched profiles.

        Returns:
            Dictionary mapping profile class names to their field values.
        """
        profile_sources: dict[str, Any] = {}
        for profile in fetched_profiles:
            if hasattr(profile, field_name):
                value = getattr(profile, field_name)
                if value is not None:
                    profile_sources[profile.__class__.__name__] = value
        return profile_sources

    def _collect_nested_profile_sources(
        self,
        nested_key: str,
        fetched_profiles: list[BaseProfile],
        parent_field_name: str,
    ) -> dict[str, Any]:
        """Collect profile sources for a nested key within a parent field.

        Traverses the nested structure in each profile to find values for the
        specified nested key path.

        Args:
            nested_key: The nested key name (e.g., 'sub_field' within a dict).
            fetched_profiles: List of successfully fetched profiles.
            parent_field_name: The name of the parent field containing the nested structure.

        Returns:
            Dictionary mapping profile class names to their nested field values.
        """
        profile_sources: dict[str, Any] = {}
        for profile in fetched_profiles:
            if hasattr(profile, parent_field_name):
                parent_value = getattr(profile, parent_field_name)
                if parent_value is not None:
                    # Handle dict-like parent
                    if self._is_dict_like(parent_value) and nested_key in parent_value:
                        nested_value = parent_value[nested_key]
                        if nested_value is not None:
                            profile_sources[profile.__class__.__name__] = nested_value
                    # Handle pydantic model parent
                    elif self._is_pydantic_model(parent_value) and hasattr(
                        parent_value, nested_key
                    ):
                        nested_value = getattr(parent_value, nested_key)
                        if nested_value is not None:
                            profile_sources[profile.__class__.__name__] = nested_value
        return profile_sources

    def _build_sources_and_values(
        self, env_value: Any, has_env_value: bool, profile_sources: dict[str, Any]
    ) -> tuple[list[str], dict[str, Any]]:
        """Build source names and values dictionaries for conflict detection.

        Args:
            env_value: The value from the environment (if any).
            has_env_value: Whether an environment value exists and is non-empty.
            profile_sources: Dictionary of profile names to their values.

        Returns:
            Tuple of (list of source names, dict of source names to values).
        """
        sources: list[str] = []
        values: dict[str, Any] = {}

        if has_env_value:
            sources.append("environment")
            values["environment"] = env_value

        for source_name, value in profile_sources.items():
            sources.append(source_name)
            values[source_name] = value

        return sources, values

    def _find_latest_profile(
        self, field_name: str, fetched_profiles: list[BaseProfile]
    ) -> BaseProfile | None:
        """Find the profile with the most recent last_updated_at for a given
        field.

        Args:
            field_name: The field name to check for.
            fetched_profiles: List of successfully fetched profiles.

        Returns:
            The profile with the latest update time, or None if no candidates found.
        """
        candidates = [
            p
            for p in fetched_profiles
            if hasattr(p, field_name) and getattr(p, field_name) is not None
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.last_updated_at)

    def _find_latest_profile_for_nested(
        self,
        nested_key: str,
        fetched_profiles: list[BaseProfile],
        parent_field_name: str,
    ) -> BaseProfile | None:
        """Find the profile with the most recent update time for a nested
        field.

        Args:
            nested_key: The nested key name within the parent field.
            fetched_profiles: List of successfully fetched profiles.
            parent_field_name: The name of the parent field.

        Returns:
            The profile with the latest update time that has the nested value, or None.
        """
        candidates = []
        for profile in fetched_profiles:
            if hasattr(profile, parent_field_name):
                parent_value = getattr(profile, parent_field_name)
                if parent_value is not None:
                    has_nested = False
                    if self._is_dict_like(parent_value) and nested_key in parent_value:
                        has_nested = parent_value[nested_key] is not None
                    elif self._is_pydantic_model(parent_value) and hasattr(
                        parent_value, nested_key
                    ):
                        has_nested = getattr(parent_value, nested_key) is not None
                    if has_nested:
                        candidates.append(profile)

        if not candidates:
            return None
        return max(candidates, key=lambda p: p.last_updated_at)

    def _create_conflict_record(
        self,
        key_path: str,
        sources: list[str],
        values: dict[str, Any],
        selected: str,
        selected_value: Any,
        resolution_reason: str,
    ) -> ConflictRecord:
        """Create a ConflictRecord instance for a detected conflict.

        Args:
            key_path: Full dotted path to the field (e.g., 'database.connection.host').
            sources: List of source names that provided values.
            values: Dictionary of source names to their values.
            selected: The source name that was selected.
            selected_value: The value that was selected.
            resolution_reason: Human-readable explanation of why this source was selected.

        Returns:
            A new ConflictRecord instance.
        """
        return ConflictRecord(
            key=key_path,
            sources=sources,
            values=values,
            selected=selected,
            selected_value=selected_value,
            resolution_reason=resolution_reason,
        )

    def _is_non_empty(self, value: Any) -> bool:
        """Check if a value is non-empty (for nested types).

        Empty values include None, empty dicts, empty lists/sets/tuples, etc.

        Args:
            value: The value to check.

        Returns:
            True if the value is non-empty, False otherwise.
        """
        if value is None:
            return False
        if isinstance(value, (dict, list, set, frozenset, tuple)):
            return len(value) > 0
        if isinstance(value, BaseModel):
            return True
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            try:
                return any(True for _ in value)
            except TypeError:
                return True
        return True

    def _resolve_field(
        self,
        field_name: str,
        current_value: Any,
        fetched_profiles: list[BaseProfile],
        key_path: str,
    ) -> None:
        """Resolve a single field, handling both simple and nested types.

        Determines the field type and delegates to appropriate resolution method.
        For nested types, recursively resolves child fields.

        Args:
            field_name: The name of the field to resolve.
            current_value: The current value of the field (from env or default).
            fetched_profiles: List of successfully fetched profiles.
            key_path: Full dotted path to this field for conflict recording.
        """
        field_type = self._get_field_type(field_name)

        if self._is_nested_type(field_type) or self._is_nested_value(current_value):
            self._resolve_nested_field(
                field_name=field_name,
                current_value=current_value,
                fetched_profiles=fetched_profiles,
                key_path=key_path,
            )
        else:
            self._resolve_simple_field(
                field_name=field_name,
                current_value=current_value,
                fetched_profiles=fetched_profiles,
                key_path=key_path,
            )

    def _is_nested_value(self, value: Any) -> bool:
        """Check if a value itself is a nested type (regardless of field type
        annotation).

        Args:
            value: The value to check.

        Returns:
            True if the value is a dict, pydantic model, or iterable collection.
        """
        if value is None:
            return False
        return (
            self._is_pydantic_model(value)
            or self._is_dict_like(value)
            or self._is_iterable_collection(value)
        )

    def _resolve_simple_field(
        self,
        field_name: str,
        current_value: Any,
        fetched_profiles: list[BaseProfile],
        key_path: str,
    ) -> None:
        """Resolve a simple (non-nested) field.

        Checks for conflicts between environment and profile sources.
        Environment takes precedence, otherwise the profile with the latest
        update time is selected.

        Args:
            field_name: The name of the field to resolve.
            current_value: The current value from environment or default.
            fetched_profiles: List of successfully fetched profiles.
            key_path: Full dotted path for conflict recording.
        """
        has_env_value = current_value is not None
        profile_sources = self._collect_profile_sources(field_name, fetched_profiles)
        sources, values = self._build_sources_and_values(
            current_value, has_env_value, profile_sources
        )

        if len(sources) > 1:
            # Conflict detected
            self._handle_conflict(
                field_name=field_name,
                current_value=current_value,
                has_env_value=has_env_value,
                sources=sources,
                values=values,
                fetched_profiles=fetched_profiles,
                key_path=key_path,
            )
        elif len(sources) == 1 and not has_env_value:
            # Single profile source, no env value - use profile value
            source_name = sources[0]
            setattr(self, field_name, values[source_name])
            logger.info("Resolved field '%s' from profile '%s'", key_path, source_name)

    def _handle_conflict(
        self,
        field_name: str,
        current_value: Any,
        has_env_value: bool,
        sources: list[str],
        values: dict[str, Any],
        fetched_profiles: list[BaseProfile],
        key_path: str,
    ) -> None:
        """Handle a conflict between multiple sources for a field.

        Environment always takes precedence. If no env value, the profile
        with the latest last_updated_at is selected.

        Args:
            field_name: The name of the field.
            current_value: The current value (from env if present).
            has_env_value: Whether an environment value exists.
            sources: List of source names providing values.
            values: Dictionary of source names to their values.
            fetched_profiles: List of successfully fetched profiles.
            key_path: Full dotted path for conflict recording.
        """
        if has_env_value:
            selected = "environment"
            selected_value = current_value
            resolution_reason = "Environment variable takes precedence"
        else:
            latest_profile = self._find_latest_profile(field_name, fetched_profiles)
            selected = latest_profile.__class__.__name__
            selected_value = getattr(latest_profile, field_name)
            setattr(self, field_name, selected_value)
            resolution_reason = f"Selected from profile with latest update time ({latest_profile.last_updated_at})"

        self._conflicts.append(
            self._create_conflict_record(
                key_path, sources, values, selected, selected_value, resolution_reason
            )
        )
        logger.info("Conflict resolved for '%s': selected '%s'", key_path, selected)

    def _resolve_nested_field(
        self,
        field_name: str,
        current_value: Any,
        fetched_profiles: list[BaseProfile],
        key_path: str,
    ) -> None:
        """Resolve a nested field by recursively processing its children.

        Handles three types of nested structures:
        - Pydantic models: recursively resolve each model field
        - Dictionaries: recursively resolve each key
        - Iterable collections: resolve the collection as a whole (no per-item recursion)

        Args:
            field_name: The name of the field to resolve.
            current_value: The current nested value.
            fetched_profiles: List of successfully fetched profiles.
            key_path: Full dotted path for conflict recording.
        """
        has_env_value = current_value is not None and self._is_non_empty(current_value)
        profile_sources = self._collect_profile_sources(field_name, fetched_profiles)

        # Filter out empty nested values from profiles
        profile_sources = {
            k: v for k, v in profile_sources.items() if self._is_non_empty(v)
        }

        # If current value is None but profiles have values, set from latest profile first
        if not has_env_value and profile_sources:
            sources, values = self._build_sources_and_values(
                None, False, profile_sources
            )
            if len(sources) > 1:
                # Multiple profiles have this nested field - pick latest
                latest_profile = self._find_latest_profile(field_name, fetched_profiles)
                selected_value = getattr(latest_profile, field_name)
                setattr(self, field_name, selected_value)
                current_value = selected_value

                self._conflicts.append(
                    self._create_conflict_record(
                        key_path,
                        sources,
                        values,
                        latest_profile.__class__.__name__,
                        selected_value,
                        f"Selected from profile with latest update time ({latest_profile.last_updated_at})",
                    )
                )
                logger.info("Conflict resolved for nested field '%s'", key_path)
            elif len(sources) == 1:
                source_name = sources[0]
                setattr(self, field_name, values[source_name])
                current_value = values[source_name]
                logger.info(
                    "Resolved nested field '%s' from profile '%s'",
                    key_path,
                    source_name,
                )

        # Now recursively resolve children if we have a value
        if current_value is not None:
            if self._is_pydantic_model(current_value):
                self._resolve_pydantic_model_children(
                    field_name=field_name,
                    model_value=current_value,
                    fetched_profiles=fetched_profiles,
                    key_path=key_path,
                )
            elif self._is_dict_like(current_value):
                self._resolve_dict_children(
                    field_name=field_name,
                    dict_value=current_value,
                    fetched_profiles=fetched_profiles,
                    key_path=key_path,
                )
            elif self._is_iterable_collection(current_value):
                # For iterables (lists, sets, etc.), check for conflicts at collection level
                self._resolve_iterable_field(
                    field_name=field_name,
                    current_value=current_value,
                    fetched_profiles=fetched_profiles,
                    key_path=key_path,
                    has_env_value=has_env_value,
                    profile_sources=profile_sources,
                )

    def _resolve_pydantic_model_children(
        self,
        field_name: str,
        model_value: BaseModel,
        fetched_profiles: list[BaseProfile],
        key_path: str,
    ) -> None:
        """Recursively resolve fields within a nested Pydantic model.

        Iterates through each field of the nested model and resolves conflicts
        between the current value and profile values.

        Args:
            field_name: The parent field name containing this model.
            model_value: The Pydantic model instance to resolve.
            fetched_profiles: List of successfully fetched profiles.
            key_path: Parent key path for building child paths.
        """
        for child_field_name in model_value.__class__.model_fields.keys():
            child_key_path = f"{key_path}.{child_field_name}"
            child_value = getattr(model_value, child_field_name)

            # Collect profile sources for this nested child
            profile_sources = self._collect_nested_profile_sources_for_model(
                parent_field_name=field_name,
                child_field_name=child_field_name,
                fetched_profiles=fetched_profiles,
            )

            has_child_value = child_value is not None
            sources, values = self._build_sources_and_values(
                child_value, has_child_value, profile_sources
            )

            if len(sources) > 1:
                # Conflict in nested field
                self._handle_nested_conflict(
                    model_value=model_value,
                    child_field_name=child_field_name,
                    child_value=child_value,
                    has_child_value=has_child_value,
                    sources=sources,
                    values=values,
                    fetched_profiles=fetched_profiles,
                    parent_field_name=field_name,
                    key_path=child_key_path,
                )
            elif len(sources) == 1 and not has_child_value:
                # Single source, set value
                source_name = sources[0]
                setattr(model_value, child_field_name, values[source_name])
                logger.info(
                    "Resolved nested field '%s' from '%s'", child_key_path, source_name
                )

            # Recurse if child is also nested
            updated_child_value = getattr(model_value, child_field_name)
            if updated_child_value is not None and self._is_nested_value(
                updated_child_value
            ):
                if self._is_pydantic_model(updated_child_value):
                    self._resolve_pydantic_model_children(
                        field_name=f"{field_name}.{child_field_name}",
                        model_value=updated_child_value,
                        fetched_profiles=fetched_profiles,
                        key_path=child_key_path,
                    )
                elif self._is_dict_like(updated_child_value):
                    self._resolve_dict_children(
                        field_name=f"{field_name}.{child_field_name}",
                        dict_value=updated_child_value,
                        fetched_profiles=fetched_profiles,
                        key_path=child_key_path,
                    )

    def _collect_nested_profile_sources_for_model(
        self,
        parent_field_name: str,
        child_field_name: str,
        fetched_profiles: list[BaseProfile],
    ) -> dict[str, Any]:
        """Collect profile values for a child field within a nested Pydantic
        model.

        Navigates through parent fields (which may be dot-separated) to find
        the child field value in each profile.

        Args:
            parent_field_name: Dot-separated path to the parent field.
            child_field_name: Name of the child field within the parent.
            fetched_profiles: List of successfully fetched profiles.

        Returns:
            Dictionary mapping profile class names to child field values.
        """
        profile_sources: dict[str, Any] = {}
        parent_parts = parent_field_name.split(".")

        for profile in fetched_profiles:
            # Navigate to parent
            current = profile
            valid = True
            for part in parent_parts:
                if hasattr(current, part):
                    current = getattr(current, part)
                    if current is None:
                        valid = False
                        break
                elif self._is_dict_like(current) and part in current:
                    current = current[part]
                    if current is None:
                        valid = False
                        break
                else:
                    valid = False
                    break

            if valid and current is not None:
                # Get child value
                if self._is_pydantic_model(current) and hasattr(
                    current, child_field_name
                ):
                    child_value = getattr(current, child_field_name)
                    if child_value is not None:
                        profile_sources[profile.__class__.__name__] = child_value
                elif self._is_dict_like(current) and child_field_name in current:
                    child_value = current[child_field_name]
                    if child_value is not None:
                        profile_sources[profile.__class__.__name__] = child_value

        return profile_sources

    def _handle_nested_conflict(
        self,
        model_value: BaseModel,
        child_field_name: str,
        child_value: Any,
        has_child_value: bool,
        sources: list[str],
        values: dict[str, Any],
        fetched_profiles: list[BaseProfile],
        parent_field_name: str,
        key_path: str,
    ) -> None:
        """Handle a conflict for a nested child field.

        Environment (current value) takes precedence. If no current value,
        selects from the profile with the latest update time.

        Args:
            model_value: The parent Pydantic model containing the child field.
            child_field_name: Name of the child field.
            child_value: Current value of the child field.
            has_child_value: Whether the child has a current value.
            sources: List of source names providing values.
            values: Dictionary of source names to their values.
            fetched_profiles: List of successfully fetched profiles.
            parent_field_name: Dot-separated path to parent field.
            key_path: Full dotted path for conflict recording.
        """
        if has_child_value:
            selected = "environment"
            selected_value = child_value
            resolution_reason = "Environment variable takes precedence"
        else:
            latest_profile = self._find_latest_profile_for_nested_model(
                parent_field_name=parent_field_name,
                child_field_name=child_field_name,
                fetched_profiles=fetched_profiles,
            )
            if latest_profile:
                selected = latest_profile.__class__.__name__
                selected_value = values[selected]
                setattr(model_value, child_field_name, selected_value)
                resolution_reason = f"Selected from profile with latest update time ({latest_profile.last_updated_at})"
            else:
                # Fallback: pick first available
                selected = sources[0]
                selected_value = values[selected]
                setattr(model_value, child_field_name, selected_value)
                resolution_reason = "Selected first available source"

        self._conflicts.append(
            self._create_conflict_record(
                key_path, sources, values, selected, selected_value, resolution_reason
            )
        )
        logger.info(
            "Conflict resolved for nested field '%s': selected '%s'", key_path, selected
        )

    def _find_latest_profile_for_nested_model(
        self,
        parent_field_name: str,
        child_field_name: str,
        fetched_profiles: list[BaseProfile],
    ) -> BaseProfile | None:
        """Find the profile with latest update time that has a nested child
        field.

        Args:
            parent_field_name: Dot-separated path to the parent field.
            child_field_name: Name of the child field.
            fetched_profiles: List of successfully fetched profiles.

        Returns:
            The profile with the latest update time, or None if not found.
        """
        parent_parts = parent_field_name.split(".")
        candidates = []

        for profile in fetched_profiles:
            current = profile
            valid = True
            for part in parent_parts:
                if hasattr(current, part):
                    current = getattr(current, part)
                    if current is None:
                        valid = False
                        break
                elif self._is_dict_like(current) and part in current:
                    current = current[part]
                    if current is None:
                        valid = False
                        break
                else:
                    valid = False
                    break

            if valid and current is not None:
                has_child = False
                if self._is_pydantic_model(current) and hasattr(
                    current, child_field_name
                ):
                    has_child = getattr(current, child_field_name) is not None
                elif self._is_dict_like(current) and child_field_name in current:
                    has_child = current[child_field_name] is not None

                if has_child:
                    candidates.append(profile)

        if not candidates:
            return None
        return max(candidates, key=lambda p: p.last_updated_at)

    def _resolve_dict_children(
        self,
        field_name: str,
        dict_value: Mapping,
        fetched_profiles: list[BaseProfile],
        key_path: str,
    ) -> None:
        """Recursively resolve fields within a nested dictionary.

        Iterates through each key in the dictionary and resolves conflicts
        between the current value and profile values.

        Args:
            field_name: The parent field name containing this dict.
            dict_value: The dictionary to resolve.
            fetched_profiles: List of successfully fetched profiles.
            key_path: Parent key path for building child paths.
        """
        # Convert to mutable dict if needed
        if not isinstance(dict_value, dict):
            return  # Can't modify non-dict mappings

        for dict_key, child_value in list(dict_value.items()):
            child_key_path = f"{key_path}.{dict_key}"

            # Collect profile sources for this dict key
            profile_sources = self._collect_nested_profile_sources_for_dict(
                parent_field_name=field_name,
                dict_key=dict_key,
                fetched_profiles=fetched_profiles,
            )

            has_child_value = child_value is not None
            sources, values = self._build_sources_and_values(
                child_value, has_child_value, profile_sources
            )

            if len(sources) > 1:
                # Conflict in dict key
                self._handle_dict_key_conflict(
                    dict_value=dict_value,
                    dict_key=dict_key,
                    child_value=child_value,
                    has_child_value=has_child_value,
                    sources=sources,
                    values=values,
                    fetched_profiles=fetched_profiles,
                    parent_field_name=field_name,
                    key_path=child_key_path,
                )
            elif len(sources) == 1 and not has_child_value:
                source_name = sources[0]
                dict_value[dict_key] = values[source_name]
                logger.info(
                    "Resolved dict key '%s' from '%s'", child_key_path, source_name
                )

            # Recurse if child is also nested
            updated_child_value = dict_value.get(dict_key)
            if updated_child_value is not None and self._is_nested_value(
                updated_child_value
            ):
                if self._is_pydantic_model(updated_child_value):
                    self._resolve_pydantic_model_children(
                        field_name=f"{field_name}.{dict_key}",
                        model_value=updated_child_value,
                        fetched_profiles=fetched_profiles,
                        key_path=child_key_path,
                    )
                elif self._is_dict_like(updated_child_value):
                    self._resolve_dict_children(
                        field_name=f"{field_name}.{dict_key}",
                        dict_value=updated_child_value,
                        fetched_profiles=fetched_profiles,
                        key_path=child_key_path,
                    )

    def _collect_nested_profile_sources_for_dict(
        self, parent_field_name: str, dict_key: str, fetched_profiles: list[BaseProfile]
    ) -> dict[str, Any]:
        """Collect profile values for a key within a nested dictionary.

        Args:
            parent_field_name: Dot-separated path to the parent field.
            dict_key: The dictionary key to find values for.
            fetched_profiles: List of successfully fetched profiles.

        Returns:
            Dictionary mapping profile class names to the dict key values.
        """
        profile_sources: dict[str, Any] = {}
        parent_parts = parent_field_name.split(".")

        for profile in fetched_profiles:
            current = profile
            valid = True
            for part in parent_parts:
                if hasattr(current, part):
                    current = getattr(current, part)
                    if current is None:
                        valid = False
                        break
                elif self._is_dict_like(current) and part in current:
                    current = current[part]
                    if current is None:
                        valid = False
                        break
                else:
                    valid = False
                    break

            if valid and current is not None and self._is_dict_like(current):
                if dict_key in current and current[dict_key] is not None:
                    profile_sources[profile.__class__.__name__] = current[dict_key]

        return profile_sources

    def _handle_dict_key_conflict(
        self,
        dict_value: dict,
        dict_key: str,
        child_value: Any,
        has_child_value: bool,
        sources: list[str],
        values: dict[str, Any],
        fetched_profiles: list[BaseProfile],
        parent_field_name: str,
        key_path: str,
    ) -> None:
        """Handle a conflict for a dictionary key.

        Args:
            dict_value: The parent dictionary.
            dict_key: The key with the conflict.
            child_value: Current value at the key.
            has_child_value: Whether there's a current value.
            sources: List of source names providing values.
            values: Dictionary of source names to their values.
            fetched_profiles: List of successfully fetched profiles.
            parent_field_name: Dot-separated path to parent field.
            key_path: Full dotted path for conflict recording.
        """
        if has_child_value:
            selected = "environment"
            selected_value = child_value
            resolution_reason = "Environment variable takes precedence"
        else:
            latest_profile = self._find_latest_profile_for_dict_key(
                parent_field_name=parent_field_name,
                dict_key=dict_key,
                fetched_profiles=fetched_profiles,
            )
            if latest_profile:
                selected = latest_profile.__class__.__name__
                selected_value = values[selected]
                dict_value[dict_key] = selected_value
                resolution_reason = f"Selected from profile with latest update time ({latest_profile.last_updated_at})"
            else:
                selected = sources[0]
                selected_value = values[selected]
                dict_value[dict_key] = selected_value
                resolution_reason = "Selected first available source"

        self._conflicts.append(
            self._create_conflict_record(
                key_path, sources, values, selected, selected_value, resolution_reason
            )
        )
        logger.info(
            "Conflict resolved for dict key '%s': selected '%s'", key_path, selected
        )

    def _find_latest_profile_for_dict_key(
        self, parent_field_name: str, dict_key: str, fetched_profiles: list[BaseProfile]
    ) -> BaseProfile | None:
        """Find the profile with latest update time that has a specific dict
        key.

        Args:
            parent_field_name: Dot-separated path to the parent dict field.
            dict_key: The dictionary key to look for.
            fetched_profiles: List of successfully fetched profiles.

        Returns:
            The profile with the latest update time, or None if not found.
        """
        parent_parts = parent_field_name.split(".")
        candidates = []

        for profile in fetched_profiles:
            current = profile
            valid = True
            for part in parent_parts:
                if hasattr(current, part):
                    current = getattr(current, part)
                    if current is None:
                        valid = False
                        break
                elif self._is_dict_like(current) and part in current:
                    current = current[part]
                    if current is None:
                        valid = False
                        break
                else:
                    valid = False
                    break

            if valid and current is not None and self._is_dict_like(current):
                if dict_key in current and current[dict_key] is not None:
                    candidates.append(profile)

        if not candidates:
            return None
        return max(candidates, key=lambda p: p.last_updated_at)

    def _resolve_iterable_field(
        self,
        field_name: str,
        current_value: Any,
        fetched_profiles: list[BaseProfile],
        key_path: str,
        has_env_value: bool,
        profile_sources: dict[str, Any],
    ) -> None:
        """Resolve an iterable collection field (list, set, tuple, etc.).

        Iterable collections are resolved as a whole - no per-item recursion.
        Conflicts are detected and resolved at the collection level.

        Args:
            field_name: The name of the field.
            current_value: The current iterable value.
            fetched_profiles: List of successfully fetched profiles.
            key_path: Full dotted path for conflict recording.
            has_env_value: Whether there's a current value from environment.
            profile_sources: Dictionary of profile names to their iterable values.
        """
        sources, values = self._build_sources_and_values(
            current_value if has_env_value else None, has_env_value, profile_sources
        )

        if len(sources) > 1:
            self._handle_conflict(
                field_name=field_name,
                current_value=current_value,
                has_env_value=has_env_value,
                sources=sources,
                values=values,
                fetched_profiles=fetched_profiles,
                key_path=key_path,
            )

    @property
    def conflicts(self) -> list[ConflictRecord]:
        """Return the list of detected conflicts from the resolution process.

        Returns:
            List of ConflictRecord instances describing each conflict.
        """
        return self._conflicts

    def mask_sensitive(self, field_name: str, value: Any) -> str | Any:
        """
        Utility: Mask sensitive values in a config dict for logging/output.

        Args:
            field_name: The name of the field.
            value: The value to mask.

        Returns:
            Masked string representation of the value or the value
        """
        if field_name in self.sensitive_fields:
            return "****"
        return value
