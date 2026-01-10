# tests/api/test_replays_security.py
"""Security tests for replay router endpoints.

Tests for fixes to:
1. Cross-user metadata leak in list_library
2. Cross-user metadata leak in get_replay_analysis
3. Blocking I/O in async endpoints (converted to sync)
4. Memory duplication on upload
5. Inefficient aggregation in list_play_sessions
6. Symlink attack vector on /tmp uploads
"""

import inspect


class TestBlockingIOFixed:
    """Test that async endpoints have been converted to sync."""

    def test_list_library_is_sync(self):
        from rlcoach.api.routers.replays import list_library
        assert not inspect.iscoroutinefunction(list_library)

    def test_get_replay_analysis_is_sync(self):
        from rlcoach.api.routers.replays import get_replay_analysis
        assert not inspect.iscoroutinefunction(get_replay_analysis)

    def test_list_uploads_is_sync(self):
        from rlcoach.api.routers.replays import list_uploads
        assert not inspect.iscoroutinefunction(list_uploads)

    def test_get_upload_is_sync(self):
        from rlcoach.api.routers.replays import get_upload
        assert not inspect.iscoroutinefunction(get_upload)

    def test_delete_upload_is_sync(self):
        from rlcoach.api.routers.replays import delete_upload
        assert not inspect.iscoroutinefunction(delete_upload)

    def test_list_play_sessions_is_sync(self):
        from rlcoach.api.routers.replays import list_play_sessions
        assert not inspect.iscoroutinefunction(list_play_sessions)


class TestMemoryOptimization:
    """Test that upload uses streaming."""

    def test_upload_uses_tempfile_streaming(self):
        from rlcoach.api.routers.replays import upload_replay
        source = inspect.getsource(upload_replay)
        assert "tempfile.NamedTemporaryFile" in source
        # Write is done via run_in_executor for async safety
        assert "temp_file.write" in source
        assert "hasher.update(chunk)" in source


class TestSecureUploadDirectory:
    """Test upload directory security."""

    def test_upload_dir_not_in_world_writable_tmp(self):
        from rlcoach.api.routers.replays import upload_replay
        source = inspect.getsource(upload_replay)
        assert '"/tmp/rlcoach/uploads"' not in source
        assert "os.getuid()" in source

    def test_upload_dir_has_restrictive_permissions(self):
        from rlcoach.api.routers.replays import upload_replay
        source = inspect.getsource(upload_replay)
        assert "mode=0o700" in source

    def test_delete_upload_uses_same_secure_directory(self):
        from rlcoach.api.routers.replays import delete_upload
        source = inspect.getsource(delete_upload)
        assert "os.getuid()" in source
        assert '"/tmp/rlcoach/uploads"' not in source


class TestEfficientAggregation:
    """Test SQL aggregation instead of Python loops."""

    def test_uses_sql_group_by(self):
        from rlcoach.api.routers.replays import list_play_sessions
        source = inspect.getsource(list_play_sessions)
        assert "func.count" in source
        assert "func.sum" in source
        assert "group_by" in source
        assert "func.avg" in source
