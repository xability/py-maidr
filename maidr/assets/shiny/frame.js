// The script that sizes a maidr chart's frame in a Shiny app, served
// once rather than sent with every flush of the output. Written by
// maidr/util/iframe_utils.py (shiny_frame_script); do not edit by hand.
(function () {
    if (window.maidrShinyFrame) return;

        function maidrOutputWidth(iframe, keepPadding) {
            var host = iframe.parentElement;
            var pad = host && !keepPadding
                ? parseFloat(window.getComputedStyle(host).paddingRight) || 0
                : 0;
            iframe.style.marginRight = pad > 0 ? (-pad) + 'px' : '';
            return pad > 0 ? 'calc(100% + ' + pad + 'px)' : '100%';
        }
        function maidrShowField(doc, resized) {
            // maidr's braille or review field, opened below the chart, took
            // the focus before the frame grew to hold it: the browser then
            // showed what it could of it, the frame's bottom edge.
            var field = doc.activeElement;
            if (resized && field && field.matches && field.matches(
                '[id^="maidr-braille-textarea"], [id^="maidr-review-input"], '
                + '.maidr-review-input, .maidr-review-input *'
            )) {
                field.scrollIntoView({block: 'nearest', inline: 'nearest'});
            }
        }

        function maidrNotLaidOut(iframe) {
            return !!(iframe && iframe.contentWindow && !iframe.contentWindow.innerWidth);
        }

        function maidrWatch(doc, onChange) {
            var parts = '.MuiModal-root, #maidr-text-container, #maidr-rotor-area, '
                + '[id^="maidr-braille-textarea"], [id^="maidr-review-input"], '
                + '.maidr-review-input';
            function counts(node) {
                return node.nodeType === 1
                    && (node.matches(parts) || !!node.querySelector(parts));
            }
            new MutationObserver(function(records) {
                for (var i = 0; i < records.length; i++) {
                    var target = records[i].target;
                    var el = target.nodeType === 1 ? target : target.parentElement;
                    if (el && el.closest(parts)) {
                        onChange();
                        return;
                    }
                    var nodes = Array.prototype.slice.call(records[i].addedNodes)
                        .concat(Array.prototype.slice.call(records[i].removedNodes));
                    for (var j = 0; j < nodes.length; j++) {
                        if (counts(nodes[j])) {
                            onChange();
                            return;
                        }
                    }
                }
            }).observe(doc.body, {childList: true, subtree: true, characterData: true});
        }

        function maidrBoxRoom(iframe) {
            var box = iframe.parentElement;
            if (!box || !box.clientWidth) return 0;
            iframe.style.height = '0px';
            var short = box.clientHeight;
            iframe.style.height = '4000px';
            var tall = box.clientHeight;
            iframe.style.height = '0px';
            if (!(short > 0) || Math.abs(tall - short) >= 1) return 0;
            var style = iframe.ownerDocument.defaultView.getComputedStyle(box);
            return short - (parseFloat(style.paddingTop) || 0)
                - (parseFloat(style.paddingBottom) || 0);
        }
        function maidrBoxWidth(iframe) {
            var box = iframe.parentElement;
            var style = iframe.ownerDocument.defaultView.getComputedStyle(box);
            return box.clientWidth - (parseFloat(style.paddingLeft) || 0)
                - (parseFloat(style.paddingRight) || 0);
        }
        // The room kept below the chart for a line of maidr's text: one
        // line of the frame's text (line-height normal, about 1.15em; 1.25
        // to be safe) and the margins of the paragraph maidr.js sets it in,
        // 1em above and below. 52px at the frame's 16px; maidr.js 3.x takes
        // 50px for it.
        function maidrTextLine(doc) {
            var style = doc.defaultView.getComputedStyle(doc.body);
            var size = parseFloat(style.fontSize) || 16;
            var line = parseFloat(style.lineHeight);
            if (!(line > 0)) line = 1.25 * size;
            return Math.ceil(line + 2 * size);
        }
        // Whether a dialog of maidr's is open in the frame. While one is,
        // the box render_maidr puts round the frame, and the output round
        // that, are pass-through containers (display: contents), as Shiny
        // makes an output that has children, the chart is not fitted, and
        // the document has a browser's own margins above and below
        // (frame.css): the frame is then sized as a chart's frame elsewhere
        // is, and as it was before charts were fitted. They are given
        // back once the dialog has gone, or once the frame has left the
        // page -- its chart drawn again, or its output emptied, with the
        // dialog open.
        function maidrSuspendBox(iframe) {
            var doc = iframe && iframe.contentWindow && iframe.contentWindow.document;
            var open = !!(doc && doc.querySelector('.MuiDialog-root'));
            if (!iframe || open === !!iframe.maidrSuspended) return open;
            var box = iframe.parentElement;
            maidrNoAnchor(iframe);
            if (open) {
                var width = iframe.getBoundingClientRect().width;
                var held = [];
                if (box && box.classList.contains('maidr-shiny-box')) {
                    held = [box, box.parentElement];
                }
                var suspended = iframe.maidrSuspended = {held: []};
                for (var i = 0; i < held.length; i++) {
                    if (!held[i]) continue;
                    suspended.held.push([held[i], held[i].style.display]);
                    held[i].style.display = 'contents';
                }
                var chart = doc.querySelector('svg.maidr-frame-svg');
                if (chart) {
                    chart.style.width = '';
                    chart.style.height = '';
                    chart.style.maxWidth = 'none';
                }
                doc.documentElement.setAttribute('data-maidr-suspended', '');
                if (doc.body) doc.body.style.paddingTop = '';
                doc.documentElement.removeAttribute('data-maidr-fit-box');
                // The width it has, which a chart that takes its frame's
                // width keeps: given the container's, wider by the box's
                // scrollbar gutter, a Plotly chart was drawn again under the
                // dialog, and threw ('mo'). A matplotlib chart's frame is
                // as wide as the chart (resizeIframe).
                iframe.style.width = width + 'px';
                iframe.style.maxWidth = '';
                iframe.maidrHostWidth = undefined;
                var win = iframe.ownerDocument.defaultView;
                if (win.MutationObserver) {
                    suspended.gone = new win.MutationObserver(function() {
                        if (!iframe.isConnected) maidrSuspendBox(iframe);
                    });
                    suspended.gone.observe(
                        iframe.ownerDocument.body, {childList: true, subtree: true}
                    );
                }
            } else {
                var was = iframe.maidrSuspended;
                iframe.maidrSuspended = null;
                if (was.gone) was.gone.disconnect();
                for (var j = 0; j < was.held.length; j++) {
                    was.held[j][0].style.display = was.held[j][1];
                }
                if (doc) {
                    doc.documentElement.removeAttribute('data-maidr-suspended');
                    if (doc.body) doc.body.style.minHeight = '';
                    var svg = doc.querySelector('svg.maidr-frame-svg');
                    if (svg) svg.style.maxWidth = '';
                }
            }
            return open;
        }
        // The page left where it is as the box is suspended or given back,
        // as nothing moved it where the box was never suspended: the
        // browser's scroll anchoring, its anchor lost with the box, held
        // what is below the frame in place instead, and scrolled a frame
        // whose top was in the window up by all it grew, the dialog's top
        // above the window. Off, for the containers round the frame, until
        // the frame has been laid out.
        function maidrNoAnchor(iframe) {
            var win = iframe.ownerDocument.defaultView;
            var off = [];
            for (var el = iframe.parentElement; el; el = el.parentElement) {
                off.push([el, el.style.overflowAnchor]);
                el.style.overflowAnchor = 'none';
            }
            win.requestAnimationFrame(function() {
                win.requestAnimationFrame(function() {
                    for (var i = 0; i < off.length; i++) {
                        off[i][0].style.overflowAnchor = off[i][1];
                    }
                });
            });
        }
        // Holds on an element's height, each for a reason: the most of
        // them is its min-height, and its own comes back once none is left.
        function maidrHold(el, why, px) {
            if (!el) return;
            var holds = el.maidrHolds;
            if (!holds) {
                if (!(px > 0)) return;
                holds = el.maidrHolds = {own: el.style.minHeight, by: {}};
            }
            if (px > 0) holds.by[why] = px; else delete holds.by[why];
            var most = 0;
            for (var k in holds.by) most = Math.max(most, holds.by[k]);
            var want = most > 0 ? most + 'px' : holds.own;
            if (el.style.minHeight !== want) el.style.minHeight = want;
            if (!(most > 0)) el.maidrHolds = null;
        }
        // The element whose height the page sees round a frame's box: the
        // output, or, where that is a pass-through container (Shiny makes
        // an output that has children one, display: contents), the
        // nearest container round it that has a box.
        function maidrHolder(el) {
            var page = el && el.ownerDocument;
            while (el && el !== page.body
                    && page.defaultView.getComputedStyle(el).display === 'contents') {
                el = el.parentElement;
            }
            return el;
        }
        function maidrHeight(el) {
            var style = el.ownerDocument.defaultView.getComputedStyle(el);
            var height = el.getBoundingClientRect().height;
            if (style.boxSizing !== 'border-box') {
                height -= (parseFloat(style.paddingTop) || 0)
                    + (parseFloat(style.paddingBottom) || 0)
                    + (parseFloat(style.borderTopWidth) || 0)
                    + (parseFloat(style.borderBottomWidth) || 0);
            }
            return height;
        }
        // The output at the height it has while the frame is measured, at
        // no height and at 4000px for a moment: the page then stays as it
        // is. It had been clamped to what fitted, the containers round the
        // output with it, and scrolled back after. Returns what lets go.
        function maidrHoldStill(iframe) {
            var box = iframe.parentElement;
            var el = box && maidrHolder(box.parentElement);
            if (!el || el.maidrHolds) return null;
            maidrHold(el, 'measure', maidrHeight(el));
            return function() { maidrHold(el, 'measure', 0); };
        }
        // The box's scroll position, kept while the frame is measured: the
        // box alone, the output round it being held still.
        function maidrKeepBoxScroll(iframe) {
            var box = iframe.parentElement;
            if (!box || !(box.scrollTop || box.scrollLeft)) return null;
            var top = box.scrollTop;
            var left = box.scrollLeft;
            return function() {
                if (box.scrollTop === top && box.scrollLeft === left) return;
                box.scrollTo({top: top, left: left, behavior: 'instant'});
            };
        }
        // An output whose chart is about to be drawn again is held at the
        // height it has (Shiny's shiny:value comes before it is), until a
        // new frame in it has measured its chart (maidrRedrawn), until
        // there is no frame of maidr's in it, or for 10s at most. Not one
        // whose chart has a dialog open: its box is suspended.
        function maidrHoldRedraw(out) {
            var old = out.querySelectorAll('iframe[data-maidr-chart]');
            for (var i = 0; i < old.length; i++) {
                if (old[i].maidrSuspended) return;
            }
            var el = old.length && maidrHolder(out);
            if (!el) return;
            var win = out.ownerDocument.defaultView;
            // Measured before an earlier hold is let go: a chart drawn again
            // before the frame drawn last had measured its own was held at
            // that frame's 150px, and the page below it moved up.
            var px = maidrHeight(el);
            if (!(px > 0)) return;
            maidrLetGo(el);
            var redraw = el.maidrRedraw = {old: Array.prototype.slice.call(old)};
            maidrHold(el, 'redraw', px);
            redraw.timer = win.setTimeout(function() { maidrLetGo(el); }, 10000);
            if (win.MutationObserver) {
                redraw.watch = new win.MutationObserver(function() {
                    if (!out.querySelector('iframe[data-maidr-chart]')) maidrLetGo(el);
                });
                redraw.watch.observe(out, {childList: true, subtree: true});
            }
        }
        function maidrLetGo(el) {
            var redraw = el.maidrRedraw;
            if (!redraw) return;
            el.maidrRedraw = null;
            el.ownerDocument.defaultView.clearTimeout(redraw.timer);
            if (redraw.watch) redraw.watch.disconnect();
            maidrHold(el, 'redraw', 0);
        }
        // A frame that has measured its chart lets go of the output held
        // for it, the frame it replaced having gone.
        function maidrRedrawn(iframe) {
            for (var el = iframe.parentElement; el; el = el.parentElement) {
                if (el.maidrRedraw && el.maidrRedraw.old.indexOf(iframe) < 0) {
                    maidrLetGo(el);
                    return;
                }
            }
        }
        // The room kept below a fitted chart for maidr's text: a line, or
        // the lines its text takes, the most it has taken in a box of this
        // size (half the box at most; longer text is scrolled to). The
        // three lines it says as the chart takes the focus, kept to one,
        // scrolled the box 18-36px and the top of the chart, and of its
        // focus ring, out of it; kept to the most so far, the chart is not
        // resized with each announcement.
        function maidrTextRoom(doc, iframe, room, width) {
            var line = maidrTextLine(doc);
            var size = room + 'x' + width;
            if (iframe.maidrTextFor !== size) {
                iframe.maidrTextFor = size;
                iframe.maidrTextRoom = line;
            }
            var text = doc.getElementById('maidr-text-container');
            if (text && text.textContent.trim()) {
                var font = parseFloat(
                    doc.defaultView.getComputedStyle(doc.body).fontSize) || 16;
                var need = Math.ceil(text.getBoundingClientRect().height + 2 * font);
                iframe.maidrTextRoom = Math.max(iframe.maidrTextRoom,
                    Math.min(need, Math.floor(room / 2)));
            }
            return iframe.maidrTextRoom;
        }
        function maidrFitChart(doc, chart, room, width, iframe) {
            var root = doc.documentElement;
            chart.style.width = '';
            chart.style.height = '';
            chart.style.maxWidth = '';
            doc.body.style.paddingTop = '';
            if (!(room > 0) || !(width > 0)) {
                root.removeAttribute('data-maidr-fit-box');
                return;
            }
            root.setAttribute('data-maidr-fit-box', '');
            var w = chart.width.baseVal.value;
            var h = chart.height.baseVal.value;
            var space = room - maidrTextRoom(doc, iframe, room, width);
            var scale = Math.min(width / w, Math.max(space, 96) / h);
            // Its width alone: its height follows its shape, and it is never
            // wider than the frame (frame.css).
            chart.style.width = (w * scale) + 'px';
            if (space > h * scale) {
                doc.body.style.paddingTop = ((space - h * scale) / 2) + 'px';
            }
        }
        // A chart that takes its height from its container -- a Plotly
        // figure with no height of its own, a Bokeh plot stretched or
        // scaled to it, a Vega-Lite chart of height "container" -- given
        // this height. plotly.js draws it again at
        // that height later, after a debounce: the frame was measured
        // before it had, and kept the old plot's height until something
        // else measured it -- full screen left a Plotly chart's text below
        // its frame, out of sight. ``redrawn`` measures it once plotly.js, or
        // Vega, has drawn it; the height is then the one set, so that measuring
        // resizes nothing.
        function maidrFillHeight(doc, height, redrawn, keepsShape) {
            var plot = doc.querySelector(
                '.js-plotly-plot, [id^="maidr-bokeh-"][id$="-plot"], .vega-embed'
            );
            if (!plot) return;
            height = Math.max(Math.floor(height), 96);
            if (keepsShape) height = maidrKeepShape(plot, height);
            var px = height + 'px';
            if (plot.style.height === px) return;
            plot.style.height = px;
            if (plot.classList.contains('vega-embed')) {
                // Vega reads a container's height on the window's resize,
                // and draws the chart again later. Measured once it has:
                // a chart drawn shorter left the frame at its old height,
                // which nothing else measured, blank below the text.
                try {
                    var win = doc.defaultView;
                    plot.maidrRedrawn = redrawn;
                    var marks = plot.querySelector('.marks');
                    if (marks && !plot.maidrMarks && win.ResizeObserver) {
                        plot.maidrMarks = new win.ResizeObserver(function() {
                            if (plot.maidrRedrawn) plot.maidrRedrawn();
                        });
                        plot.maidrMarks.observe(marks);
                    }
                    win.dispatchEvent(new win.Event('resize'));
                } catch (_) {}
            }
            var plotly = doc.defaultView.Plotly;
            if (plot.classList.contains('js-plotly-plot') && plotly && plotly.Plots
                    && plot._fullLayout) {
                try {
                    var done = plotly.Plots.resize(plot);
                    if (done && done.then) done.then(redrawn, redrawn);
                } catch (_) {}
            }
        }
        // A Bokeh plot scaled both ways (sizing_mode="scale_both") keeps
        // its shape, and takes its size from its container's width alone:
        // given the box's height, it was as tall as it was wide, 1256px in
        // a 450px plot, and painted over maidr's text. Once Bokeh has drawn
        // it, it is kept as wide as that height allows at its shape, and
        // centred; the height it is then given is the one its width
        // allows, where that is less.
        function maidrKeepShape(plot, height) {
            var drawn = plot.firstElementChild;
            var rect = drawn && drawn.getBoundingClientRect();
            if (!rect || !(rect.width > 0) || !(rect.height > 0)) return height;
            var shape = rect.width / rect.height;
            var px = Math.floor(height * shape) + 'px';
            if (plot.style.maxWidth !== px) {
                plot.style.maxWidth = px;
                plot.style.marginLeft = 'auto';
                plot.style.marginRight = 'auto';
            }
            return Math.max(Math.min(height, Math.floor(plot.clientWidth / shape)), 96);
        }
        // A chart that takes its width from a box of a height of its own
        // keeps the box's scrollbar's room, whether the box scrolls or not.
        // Where scrollbars take room (Windows'), maidr's braille and review
        // fields and a long announcement made the box scroll and stop as
        // they came and went, and plotly.js drew the chart again at each
        // width, throwing ("reading 'mo'") while a bar was highlighted.
        function maidrKeepGutter(iframe, keep) {
            var box = iframe.parentElement;
            var gutter = keep ? 'stable' : '';
            if (box && box.style.scrollbarGutter !== gutter) {
                box.style.scrollbarGutter = gutter;
            }
        }
        // maidr's text, once it changed, in the box, which alone is
        // scrolled: as maidrShowField shows a field, without moving the page.
        function maidrShowText(doc, iframe) {
            var box = iframe.parentElement;
            var text = doc.getElementById('maidr-text-container');
            var said = text ? text.textContent : '';
            if (!box || said === iframe.maidrSaid) return;
            iframe.maidrSaid = said;
            if (!said.trim() || box.scrollHeight <= box.clientHeight + 1) return;
            var frame = iframe.getBoundingClientRect();
            var rect = text.getBoundingClientRect();
            var top = box.getBoundingClientRect().top + box.clientTop;
            var over = frame.top + rect.bottom - (top + box.clientHeight);
            var under = top - (frame.top + rect.top);
            if (under > 0) {
                box.scrollTop -= under;
            } else if (over > 0) {
                box.scrollTop += Math.min(over, -under);
            }
        }

        function maidrWatchBox(iframe, onChange) {
            var box = iframe.parentElement;
            var win = iframe.ownerDocument.defaultView;
            if (!box || !win.ResizeObserver) return;
            // One observer per box: a frame loaded again replaces its own.
            if (box.maidrBoxObserver) box.maidrBoxObserver.disconnect();
            box.maidrBoxObserver = new win.ResizeObserver(onChange);
            box.maidrBoxObserver.observe(box);
        }

    function matplotlibFrame(frame, options) {

        function resizeIframe() {
            let iframe = frame;
            let fitsOutput = !maidrSuspendBox(iframe);
            if (fitsOutput && maidrNotLaidOut(iframe)) return;
            if (
                iframe && iframe.contentWindow &&
                iframe.contentWindow.document &&
                iframe.contentWindow.document.body
            ) {
                let iframeDocument = iframe.contentWindow.document;
                let body = iframeDocument.body;
                let de = iframeDocument.documentElement;
                let letGo = fitsOutput ? maidrHoldStill(iframe) : null;
                let restoreScroll = fitsOutput ? maidrKeepBoxScroll(iframe) : null;
                let before = iframe.style.height;
                let room = 0;

                let bodyStyle = iframe.contentWindow.getComputedStyle(body);
                let side = (parseFloat(bodyStyle.marginLeft) || 0)
                    + (parseFloat(bodyStyle.marginRight) || 0);
                // In a notebook the frame is as wide as the output area, up to
                // the chart's own width, the width the svg was given (the
                // plain figure's), and the chart shrinks with it (frame.css),
                // as the figure's image shrinks to the output area. A width
                // in CSS, so the frame follows the output area as it narrows
                // or widens, with nothing to run.
                let chart = fitsOutput
                    ? iframeDocument.querySelector('svg.maidr-frame-svg')
                    : null;
                let own = chart && chart.width && chart.width.baseVal
                    ? chart.width.baseVal.value
                    : 0;
                if (own > 0) {
                    // In a Shiny app, the chart is fitted to its box when
                    // the box has a height of its own, and is then as wide
                    // as the box.
                    iframe.style.width = maidrOutputWidth(iframe, true);
                    let boxRoom = maidrBoxRoom(iframe);
                    maidrFitChart(
                        iframeDocument, chart, boxRoom, maidrBoxWidth(iframe), iframe
                    );
                    iframe.style.maxWidth = boxRoom > 0 ? '' : (own + side) + 'px';
                } else if (fitsOutput) {
                    // Until maidr.js has put the chart back: narrowed to
                    // nothing, the frame had no width to measure it at.
                    iframe.style.width = maidrOutputWidth(iframe, true);
                    iframe.style.maxWidth = '';
                } else {
                    // The width comes first, so the height below is measured
                    // at the width the frame keeps. body.scrollWidth is never
                    // less than the body's own width, so the frame is
                    // narrowed to nothing before it is read, and the content
                    // alone sets it. It is measured from the body's edge, so
                    // the body's margins are added back; without them the
                    // frame cut 8px, and the focus outline, off the chart's
                    // right side (#893).
                    iframe.style.width = '0px';
                    iframe.style.width = (body.scrollWidth + side) + 'px';
                }

                // In a notebook the height is measured with the frame at
                // none, so that the 150px an iframe is left at is no floor
                // under a short chart.
                iframe.style.height = fitsOutput ? '0px' : 'auto';

                // Use Math.max() across multiple DOM measurements (industry standard)
                let height = Math.max(
                    body.scrollHeight || 0,
                    body.offsetHeight || 0,
                    de.scrollHeight || 0,
                    de.offsetHeight || 0,
                    fitsOutput ? 0 : (de.clientHeight || 0)
                );

                // Scan specific MAIDR elements with getBoundingClientRect()
                // This ensures elements with overflow:visible parents are included
                let selectors = [
                    '#maidr-rotor-area',
                    '#maidr-text-container',
                    '[id^="maidr-braille-textarea"]',
                    '.maidr-review-input'
                ];
                for (let i = 0; i < selectors.length; i++) {
                    let el = iframeDocument.querySelector(selectors[i]);
                    if (el) {
                        let rect = el.getBoundingClientRect();
                        let bottom = rect.bottom + (iframe.contentWindow.scrollY || 0);
                        if (bottom > height) {
                            height = bottom;
                        }
                    }
                }

                // Detect braille textarea by dynamic id prefix
                let brailleContainer = iframeDocument.querySelector('[id^="maidr-braille-textarea"]');
                // Detect review input container by class name
                let reviewInputContainer = iframeDocument.querySelector('.maidr-review-input');
                // Consider braille active if it or any descendant has focus
                let isBrailleActive = brailleContainer && (
                    brailleContainer === iframeDocument.activeElement ||
                    (typeof brailleContainer.contains === 'function' && brailleContainer.contains(iframeDocument.activeElement))
                );
                // Consider review input active if it or any descendant has focus
                let isReviewInputActive = reviewInputContainer && (
                    reviewInputContainer === iframeDocument.activeElement ||
                    (typeof reviewInputContainer.contains === 'function' && reviewInputContainer.contains(iframeDocument.activeElement))
                );

                // Add buffer for active states (rotor-area height is measured directly above)
                if (isBrailleActive) {
                    height += 100;
                } else if (isReviewInputActive) {
                    height += 50;
                }
                height = Math.max(height, room);
                iframe.style.height = (height) + 'px';
                if (restoreScroll) restoreScroll();
                if (letGo) letGo();
                if (fitsOutput && own > 0) maidrRedrawn(iframe);
                if (fitsOutput) {
                    let resized = iframe.style.height !== before;
                    maidrShowField(iframeDocument, resized);
                }
                if (fitsOutput) maidrShowText(iframeDocument, iframe);
            }
        }
        let iframe = frame;
        resizeIframe();
        // Delegate focus events for braille textarea (by id prefix)
        iframe.contentWindow.document.addEventListener('focusin', (e) => {
            try {
                const t = e && e.target ? e.target : null;
                if (t && typeof t.id === 'string' && t.id.startsWith('maidr-braille-textarea')) resizeIframe();
            } catch (_) { resizeIframe(); }
        }, true);
        iframe.contentWindow.document.addEventListener('focusout', (e) => {
            try {
                const t = e && e.target ? e.target : null;
                if (t && typeof t.id === 'string' && t.id.startsWith('maidr-braille-textarea')) resizeIframe();
            } catch (_) { resizeIframe(); }
        }, true);
        // Delegate focus events for review input container (by class name)
        iframe.contentWindow.document.addEventListener('focusin', (e) => {
            try {
                const t = e && e.target ? e.target : null;
                if (t && t.classList && t.classList.contains('maidr-review-input')) resizeIframe();
            } catch (_) { resizeIframe(); }
        }, true);
        iframe.contentWindow.document.addEventListener('focusout', (e) => {
            try {
                const t = e && e.target ? e.target : null;
                if (t && t.classList && t.classList.contains('maidr-review-input')) resizeIframe();
            } catch (_) { resizeIframe(); }
        }, true);
        // Modern resize detection: ResizeObserver with MutationObserver fallback
        try {
            let rafId = 0;
            let scheduleResize = function() {
                cancelAnimationFrame(rafId);
                rafId = requestAnimationFrame(function() {
                    resizeIframe();
                });
            };

            var lastWidth = iframe.contentWindow.innerWidth;
            iframe.contentWindow.addEventListener('resize', function() {
                var width = iframe.contentWindow.innerWidth;
                if (width !== lastWidth) {
                    lastWidth = width;
                    scheduleResize();
                }
            });
            iframe.contentWindow.document.addEventListener('focusin', scheduleResize, true);
            iframe.contentWindow.document.addEventListener('focusout', scheduleResize, true);
            maidrWatch(iframe.contentWindow.document, scheduleResize);
            var chartBack = new MutationObserver(function() {
                if (iframe.contentWindow.document.querySelector('svg.maidr-frame-svg')) {
                    chartBack.disconnect();
                    scheduleResize();
                }
            });
            chartBack.observe(
                iframe.contentWindow.document.body, { childList: true, subtree: true }
            );

            maidrWatchBox(iframe, scheduleResize);

            // Try ResizeObserver first (modern, more efficient)
            if (typeof iframe.contentWindow.ResizeObserver !== 'undefined') {
                new iframe.contentWindow.ResizeObserver(scheduleResize).observe(
                    iframe.contentWindow.document.body
                );
            } else {
                // Fallback to MutationObserver (observe entire document for all changes)
                new MutationObserver(scheduleResize).observe(
                    iframe.contentWindow.document.body,
                    { childList: true, subtree: true, characterData: true, attributes: true }
                );
            }
        } catch (_) {}

    }
    function plotlyFrame(frame, options) {

        function resizeIframe() {
            var iframe = frame;
            if (!iframe || !iframe.contentWindow || !iframe.contentWindow.document) {
                return;
            }
            var fitsOutput = !maidrSuspendBox(iframe);
            var keepsPadding = true;
            var widens = options.widens;

            if (fitsOutput && maidrNotLaidOut(iframe)) return;
            var doc = iframe.contentWindow.document;
            var body = doc.body;
            if (!body) return;
            var de = doc.documentElement;
            var letGo = fitsOutput ? maidrHoldStill(iframe) : null;
            var restoreScroll = fitsOutput ? maidrKeepBoxScroll(iframe) : null;
            var before = iframe.style.height;
            var room = 0;
            // In a Shiny app: the room the box gives the chart (none when
            // the box takes its height from the frame), and a chart that
            // takes its height from its container as tall as that room
            // less the line kept for maidr's text, or, with none,
            // options.fillHeight; see _BOX_JS. While a dialog is open, it
            // is left as it is -- drawn again under a dialog, a Plotly
            // chart threw ('mo') and lost its highlight -- and the frame
            // is at least as tall as in an output with no height of its
            // own.
            var boxRoom = fitsOutput ? maidrBoxRoom(iframe) : 0;
            maidrKeepGutter(iframe, boxRoom > 0 && !widens);
            if (options.fillHeight && fitsOutput) {
                maidrFillHeight(doc, boxRoom > 0
                    ? boxRoom - maidrTextLine(doc)
                    : options.fillHeight, function() {
                        requestAnimationFrame(resizeIframe);
                    }, options.keepsShape);
            }
            body.style.minHeight = options.fillHeight && !fitsOutput
                ? (options.fillHeight + maidrTextLine(doc)) + 'px' : '';

            // WIDTH, in a notebook: a chart of a fixed width wider than the
            // output area widens the frame, so the output area scrolls to it
            // as it does to the plain chart, where scrolling="no" cut it off.
            // One that takes the frame's width never overflows it. The
            // frame is given the output area's width again only when that
            // has changed.
            if (fitsOutput) {
                var host = iframe.parentElement;
                var hostWidth = host ? host.clientWidth : 0;
                if (iframe.maidrHostWidth !== hostWidth) {
                    iframe.maidrHostWidth = hostWidth;
                    iframe.style.width = maidrOutputWidth(iframe, keepsPadding);
                }
                if (widens && de.scrollWidth > iframe.contentWindow.innerWidth + 1) {
                    iframe.style.width = de.scrollWidth + 'px';
                }
            }

            // CRITICAL: Shrink iframe first to get accurate content measurement.
            // Without this, body.scrollHeight reflects the current iframe size,
            // not the natural content size (causes whitespace after braille closes).
            // In a notebook to no height at all, so that the 150px an iframe is
            // left at is no floor under the document's own height, which is
            // measured there too: it counts the margins of what the document
            // starts and ends with, which body.scrollHeight leaves out.
            iframe.style.height = fitsOutput ? '0px' : 'auto';

            // HEIGHT: Measure content after shrinking
            var height = Math.max(
                body.scrollHeight || 0,
                body.offsetHeight || 0,
                fitsOutput ? (de.scrollHeight || 0) : 0,
                fitsOutput ? (de.offsetHeight || 0) : 0
            );

            // Scan MAIDR elements for bottom edge (they extend below the chart)
            var heightSelectors = [
                'svg.main-svg',
                '#maidr-rotor-area',
                '#maidr-text-container',
                '[id^="maidr-braille-textarea"]',
                '[id^="maidr-review-input"]'
            ];
            for (var i = 0; i < heightSelectors.length; i++) {
                var el = doc.querySelector(heightSelectors[i]);
                if (el) {
                    var rect = el.getBoundingClientRect();
                    var bottom = rect.bottom + (iframe.contentWindow.scrollY || 0);
                    if (bottom > height) {
                        height = bottom;
                    }
                }
            }

            // Buffer for braille/review active states
            var braille = doc.querySelector('[id^="maidr-braille-textarea"]');
            var review = doc.querySelector('[id^="maidr-review-input"]');
            var isBrailleActive = braille && (
                braille === doc.activeElement ||
                braille.contains(doc.activeElement)
            );
            var isReviewActive = review && (
                review === doc.activeElement ||
                review.contains(doc.activeElement)
            );
            if (isBrailleActive) {
                height += 100;
            } else if (isReviewActive) {
                height += 50;
            }
            height = Math.max(height, room);

            iframe.style.height = height + 'px';
            if (restoreScroll) restoreScroll();
            if (letGo) letGo();
            if (doc.querySelector('[role=img], [role=application]')) {
                maidrRedrawn(iframe);
            }
            if (fitsOutput) {
                var resized = iframe.style.height !== before;
                maidrShowField(doc, resized);
            }
            if (fitsOutput) maidrShowText(doc, iframe);
        }

        var iframe = frame;
        resizeIframe();

        // Measure again when the frame's window changes width. Its height is
        // set here, and the window is resized when it is, measured at
        // 'auto' or none included, which measured the frame again on every
        // frame, for as long as the page was open.
        try {
            var lastWidth = iframe.contentWindow.innerWidth;
            iframe.contentWindow.addEventListener('resize', function() {
                var width = iframe.contentWindow.innerWidth;
                if (width !== lastWidth) {
                    lastWidth = width;
                    resizeIframe();
                }
            });
        } catch (_) {}

        // Delayed retries to catch async MAIDR content (plotly.js + maidr.js loading)
        setTimeout(resizeIframe, 500);
        setTimeout(resizeIframe, 1500);
        setTimeout(resizeIframe, 3000);

        // ResizeObserver with MutationObserver fallback for DOM changes
        try {
            var _raf = 0;
            var scheduleResize = function() {
                cancelAnimationFrame(_raf);
                _raf = requestAnimationFrame(resizeIframe);
            };

            // maidr's text and fields, which can lie past the body's box, and
            // a dialog maidr opens or closes, which needs room or gives it back.
            maidrWatch(iframe.contentWindow.document, scheduleResize);
            maidrWatchBox(iframe, scheduleResize);

            if (typeof iframe.contentWindow.ResizeObserver !== 'undefined') {
                new iframe.contentWindow.ResizeObserver(scheduleResize).observe(
                    iframe.contentWindow.document.body
                );
            } else {
                new MutationObserver(scheduleResize).observe(
                    iframe.contentWindow.document.body,
                    { childList: true, subtree: true, characterData: true, attributes: true }
                );
            }
        } catch (_) {}

        // Focus events for braille/review buffer changes
        try {
            iframe.contentWindow.document.addEventListener('focusin', resizeIframe, true);
            iframe.contentWindow.document.addEventListener('focusout', resizeIframe, true);
        } catch (_) {}

    }
    window.maidrShinyFrame = function (frame, kind, options) {
        (kind === 'plotly' ? plotlyFrame : matplotlibFrame)(frame, options || {});
    };
    if (window.jQuery) {
        // Shiny runs this in its message loop, where an error stops the
        // outputs after this one from updating; and an output Shiny has no
        // binding for sends its value to the document itself.
        window.jQuery(document).on('shiny:value', function (event) {
            try {
                if (event.target && event.target.nodeType === 1) {
                    maidrHoldRedraw(event.target);
                }
            } catch (e) {}
        });
    }
})();
