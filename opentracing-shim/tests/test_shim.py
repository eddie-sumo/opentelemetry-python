# Copyright 2019, OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest

import opentracing

import opentracingshim
from opentelemetry import trace
from opentelemetry.sdk.trace import Tracer


class TestShim(unittest.TestCase):
    def setUp(self):
        self.tracer = trace.tracer()
        self.shim = opentracingshim.create_tracer(self.tracer)

    @classmethod
    def setUpClass(cls):
        """Set preferred tracer implementation only once rather than before
        every test method.
        """
        # TODO: Do we need to call setUpClass() on super()?
        # Seems to work fine without it.
        super(TestShim, cls).setUpClass()
        trace.set_preferred_tracer_implementation(lambda T: Tracer())

    def test_shim_type(self):
        # Verify shim is an OpenTracing tracer.
        self.assertIsInstance(self.shim, opentracing.Tracer)

    def test_basic_behavior(self):
        """Test span creation, activation and deactivation."""

        with self.shim.start_active_span("TestSpan") as scope:
            # Verify correct type of Scope and Span objects.
            self.assertIsInstance(scope, opentracing.Scope)
            self.assertIsInstance(scope.span, opentracing.Span)

            # Verify the span is started.
            self.assertIsNotNone(scope.span.otel_span.start_time)

            # Verify the span is active in the OpenTelemetry tracer.
            # TODO: We can't check for equality of self.shim.active_span and
            # scope.span because the same OpenTelemetry span is returned inside
            # different SpanWrapper objects. A possible solution is described
            # here:
            # https://github.com/open-telemetry/opentelemetry-python/issues/161#issuecomment-534136274
            self.assertEqual(self.shim.active_span.context, scope.span.context)

        # Verify the span has ended in the OpenTelemetry tracer.
        self.assertIsNotNone(scope.span.otel_span.end_time)

        # Verify no span is active on the OpenTelemetry tracer.
        self.assertIsNone(self.tracer.get_current_span())

    def test_start_span(self):
        """Test span creation using `start_span()`."""

        with self.shim.start_span("TestSpan") as span:
            # Verify correct type of Span object.
            self.assertIsInstance(span, opentracing.Span)

            # Verify the span is started.
            self.assertIsNotNone(span.otel_span.start_time)

        # Verify the span has ended in the OpenTelemetry tracer.
        self.assertIsNotNone(span.otel_span.end_time)

        # Verify `start_span()` does NOT make the span active.
        self.assertIsNone(self.shim.active_span)

    def test_explicit_start_time(self):
        """Test `start_time` argument."""

        now = opentracingshim.util.time_ns()
        with self.shim.start_active_span("TestSpan", start_time=now) as scope:
            self.assertEqual(scope.span.otel_span.start_time, now)

    def test_start_span_no_contextmanager(self):
        """Test `start_span()` without a `with` statement."""

        span = self.shim.start_span("TestSpan")

        # Verify the span is started.
        self.assertIsNotNone(span.otel_span.start_time)

        # Verify `start_span()` does NOT make the span active.
        self.assertIsNone(self.shim.active_span)

        span.finish()

        # Verify the span has ended in the OpenTelemetry tracer.
        self.assertIsNotNone(span.otel_span.end_time)

    def test_parent_child_implicit(self):
        """Test parent-child relationship of spans without specifying the
        parent span upon creation, as well as span activation/deactivation.
        """

        with self.shim.start_active_span("ParentSpan") as parent:
            # Verify parent span is the active span.
            self.assertEqual(
                self.shim.active_span.context, parent.span.context
            )

            with self.shim.start_active_span("ChildSpan") as child:
                # Verify child span is the active span.
                self.assertEqual(
                    self.shim.active_span.context, child.span.context
                )

                # Verify parent-child relationship.
                parent_trace_id = parent.span.otel_span.get_context().trace_id
                child_trace_id = child.span.otel_span.get_context().trace_id

                self.assertEqual(parent_trace_id, child_trace_id)
                self.assertEqual(
                    child.span.otel_span.parent, parent.span.otel_span
                )

            # Verify parent span becomes the active span again.
            self.assertEqual(
                self.shim.active_span.context,
                parent.span.context
                # TODO: Check equality of the spans themselves rather than
                # their context once the SpanWrapper reconstruction problem
                # has been addressed (see previous TODO).
            )

        # Verify there is no active span.
        self.assertIsNone(self.shim.active_span)

    def test_parent_child_explicit_span(self):
        """Test parent-child relationship of spans when specifying a `Span`
        object as a parent upon creation.
        """

        # TODO: Test explicit parent also with `start_active_span()`.

        parent = self.shim.start_span("ParentSpan")
        child = self.shim.start_span("ChildSpan", child_of=parent)

        parent_trace_id = parent.otel_span.get_context().trace_id
        child_trace_id = child.otel_span.get_context().trace_id

        self.assertEqual(child_trace_id, parent_trace_id)
        self.assertEqual(child.otel_span.parent, parent.otel_span)

    def test_parent_child_explicit_span_context(self):
        """Test parent-child relationship of spans when specifying a
        `SpanContext` object as a parent upon creation.
        """

        # TODO: Test explicit parent also with `start_active_span()`.

        parent = self.shim.start_span("ParentSpan")
        child = self.shim.start_span(
            "SpanWithContextParent", child_of=parent.context
        )

        parent_trace_id = parent.otel_span.get_context().trace_id
        child_trace_id = child.otel_span.get_context().trace_id

        self.assertEqual(child_trace_id, parent_trace_id)
        self.assertEqual(child.otel_span.parent, parent.context.otel_context)

    def test_references(self):
        """Test span creation using the `references` argument."""

        parent = self.shim.start_span("ParentSpan")
        ref = opentracing.child_of(parent.context)
        child = self.shim.start_span("ChildSpan", references=[ref])

        self.assertEqual(
            child.otel_span.links[0].context, parent.context.otel_context
        )

    def test_explicit_span_activation(self):
        """Test manual activation and deactivation of a span."""

        span = self.shim.start_span("TestSpan")

        # Verify no span is currently active.
        self.assertIsNone(self.shim.active_span)

        with self.shim.scope_manager.activate(
            span, finish_on_close=True
        ) as scope:
            # Verify span is active.
            self.assertEqual(self.shim.active_span.context, scope.span.context)

        # Verify no span is active.
        self.assertIsNone(self.shim.active_span)

    def test_set_operation_name(self):
        with self.shim.start_active_span("TestName") as scope:
            self.assertEqual(scope.span.otel_span.name, "TestName")

            scope.span.set_operation_name("NewName")
            self.assertEqual(scope.span.otel_span.name, "NewName")

    def test_tags(self):
        """Test tags behavior."""

        tags = {"foo": "bar"}
        with self.shim.start_active_span("TestSetTag", tags=tags) as scope:
            scope.span.set_tag("baz", "qux")

            self.assertEqual(scope.span.otel_span.attributes["foo"], "bar")
            self.assertEqual(scope.span.otel_span.attributes["baz"], "qux")

    def test_span(self):
        # Test tracer property.
        span = self.shim.start_span("TestSpan")
        self.assertEqual(span.tracer, self.shim)

        # Test finish() on span.
        self.assertIsNone(span.otel_span.end_time)
        span.finish()
        self.assertIsNotNone(span.otel_span.end_time)

    def test_log_kv(self):
        span = self.shim.start_span("TestSpan")

        span.log_kv({"foo": "bar"})
        self.assertEqual(span.otel_span.events[0].attributes["foo"], "bar")
        # Verify timestamp was generated automatically.
        self.assertIsNotNone(span.otel_span.events[0].timestamp)

        # Test explicit timestamp.
        now = opentracingshim.util.time_ns()
        span.log_kv({"foo": "bar"}, now)
        self.assertEqual(span.otel_span.events[1].timestamp, now)

    def test_span_context(self):
        otel_context = trace.SpanContext(1234, 5678)
        context = opentracingshim.SpanContextWrapper(otel_context)

        self.assertIsInstance(context, opentracing.SpanContext)
        self.assertEqual(context.otel_context.trace_id, 1234)
        self.assertEqual(context.otel_context.span_id, 5678)

    def test_explicit_scope_close(self):
        """Test `close()` method on `ScopeWrapper`."""

        span = self.shim.start_span("TestSpan")
        scope = opentracingshim.ScopeWrapper(self.shim.scope_manager, span)

        # Verify span hasn't ended.
        self.assertIsNone(span.otel_span.end_time)

        scope.close()

        # Verify span has ended.
        self.assertIsNotNone(span.otel_span.end_time)

    # TODO: Test finish_on_close on `start_active_span()``.
