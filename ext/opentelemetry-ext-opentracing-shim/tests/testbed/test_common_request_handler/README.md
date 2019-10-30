# Common Request Handler example.

This example shows a `Span` used with `RequestHandler`, which is used as a middleware (as in web frameworks) to manage a new `Span` per operation through its `before_request()`/`after_response()` methods.

Implementation details:
- For `threading`, no active `Span` is consumed as the tasks may be run concurrently on different threads, and an explicit `SpanContext` has to be saved to be used as parent.
- For `gevent` and `asyncio`, as no automatic `Span` propagation is done, an explicit `Span` has to be saved to be used as parent (observe an instrumentation library could help to do that implicitly - we stick to the simplest case, though).
- For `tornado`, as the `StackContext` automatically propapates the context (even is the tasks are called through different coroutines), we **do** leverage the active `Span`.


RequestHandler implementation:
```python
    def before_request(self, request, request_context):

        # If we should ignore the active Span, use any passed SpanContext
        # as the parent. Else, use the active one.
        if self.ignore_active_span:
            # Used by threading, gevent and asyncio.
            span = self.tracer.start_span('send',
                                          child_of=self.context,
                                          ignore_active_span=True)
        else:
            # Used by tornado.
            span = self.tracer.start_span('send')
```
