// The script that sizes a maidr chart's frame in a Shiny app, served
// once rather than sent with every flush of the output. Written by
// maidr/util/iframe_utils.py (shiny_frame_script); do not edit by hand.
(function () {
    // One copy per kind of chart is enough: a frame that carries its
    // script (_shiny_onload) brings its own kind's alone.
    var kinds = window.maidrShinyKinds = window.maidrShinyKinds || {};
    if (kinds.matplotlib && kinds.plotly) return;

        function maidrOutputWidth(iframe, keepPadding) {
            var host = iframe.parentElement;
            var pad = host && !keepPadding
                ? parseFloat(window.getComputedStyle(host).paddingRight) || 0
                : 0;
            iframe.style.marginRight = pad > 0 ? (-pad) + 'px' : '';
            return pad > 0 ? 'calc(100% + ' + pad + 'px)' : '100%';
        }

        function maidrKeepScroll(iframe) {
            var page = iframe.ownerDocument;
            var frame = iframe.getBoundingClientRect();
            var kept = [];
            for (var el = iframe.parentElement; el; el = el.parentElement) {
                if (el.scrollTop || el.scrollLeft) {
                    var whole = el === page.documentElement || el === page.body;
                    var shown = whole ? 0 : el.getBoundingClientRect().top + el.clientTop;
                    kept.push([el, el.scrollTop, el.scrollLeft, frame.bottom <= shown]);
                }
            }
            return function() {
                var grew = iframe.getBoundingClientRect().height - frame.height;
                for (var i = 0; i < kept.length; i++) {
                    var el = kept[i][0];
                    var top = kept[i][1] + (kept[i][3] ? grew : 0);
                    if (el.scrollTop !== top || el.scrollLeft !== kept[i][2]) {
                        el.scrollTo({top: top, left: kept[i][2], behavior: 'instant'});
                    }
                }
            };
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

        function maidrDialogRoom(doc, iframe) {
            if (!doc.querySelector('.MuiDialog-root')) return 0;
            var win = iframe.ownerDocument.defaultView;
            var height = win.innerHeight || 0;
            var scroller = null;
            for (var el = iframe.parentElement; el; el = el.parentElement) {
                var y = win.getComputedStyle(el).overflowY;
                if ((y === 'auto' || y === 'scroll' || y === 'overlay')
                        && el.scrollHeight > el.clientHeight + 1) {
                    scroller = el;
                }
            }
            if (scroller) {
                height = Math.min(height, scroller.clientHeight);
            } else if (win !== win.top) {
                height = Math.max(height, 480);
            }
            return Math.floor(height);
        }
        function maidrShowDialog(doc, iframe, room, resized) {
            var opened = room > 0;
            var was = iframe.maidrDialogOpen;
            iframe.maidrDialogOpen = opened;
            // Over a chart taller than the reader's view, the dialog is kept
            // to a band of that height in the middle of the frame (frame.css).
            var root = doc.documentElement;
            if (opened && iframe.clientHeight > room) {
                root.style.setProperty('--maidr-dialog-room', room + 'px');
                root.setAttribute('data-maidr-dialog-room', '');
            } else if (root.hasAttribute('data-maidr-dialog-room')) {
                root.style.removeProperty('--maidr-dialog-room');
                root.removeAttribute('data-maidr-dialog-room');
            }
            if (opened && (!was || resized)) {
                // The dialog is centred in the frame: centring the frame in
                // the reader's view shows it whole.
                iframe.scrollIntoView({block: 'center', inline: 'nearest', behavior: 'instant'});
            }
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
        // the frame is laid out as before charts were fitted to their
        // outputs, by construction: the box render_maidr puts round it is
        // a pass-through container (display: contents), as if it were not
        // there; the output round that has none of the style or fill
        // classes output_maidr gives it, so that Shiny's own rule makes it
        // one too; the frame has an iframe's style as it had then; and the
        // frame's script sizes it, gives the dialog room and scrolls it
        // into view as a notebook's frame does (the lines marked for
        // every frame but a Shiny app's, and maidrDialogRoom). All of it
        // is given back once the dialog closes -- as MUI gives the chart
        // the focus back, before the browser scrolls to it -- or once the
        // frame has left the page: its chart drawn again, or its output
        // emptied, with the dialog open. The chart is then fitted again.
        function maidrSuspendBox(iframe) {
            var doc = iframe && iframe.contentWindow && iframe.contentWindow.document;
            var roots = doc ? doc.querySelectorAll('.MuiDialog-root') : [];
            var open = false;
            for (var r = 0; r < roots.length; r++) open = open || !roots[r].maidrClosed;
            var active = doc && doc.activeElement;
            if (open && iframe.maidrSuspended && active && active !== doc.body
                    && !active.closest('.MuiModal-root')) {
                // Closing, though it has yet to fade out: the focus has
                // left it, for the chart.
                for (var c = 0; c < roots.length; c++) roots[c].maidrClosed = true;
                open = false;
            }
            if (!iframe || open === !!iframe.maidrSuspended) return open;
            var box = iframe.parentElement;
            iframe.maidrHostWidth = undefined;
            if (open) {
                var width = iframe.getBoundingClientRect().width;
                var suspended = iframe.maidrSuspended = {
                    frame: iframe.getAttribute('style'), held: [],
                    kept: maidrKeepPlace(iframe)
                };
                if (box && box.classList.contains('maidr-shiny-box')) {
                    suspended.held.push([box, box.getAttribute('style'), []]);
                    box.setAttribute('style', 'display: contents');
                    var out = box.parentElement;
                    if (out && out.classList.contains('shiny-html-output')) {
                        var fill = ['html-fill-container', 'html-fill-item']
                            .filter(function(name) { return out.classList.contains(name); });
                        suspended.held.push([out, out.getAttribute('style'), fill]);
                        out.removeAttribute('style');
                        for (var i = 0; i < fill.length; i++) out.classList.remove(fill[i]);
                    }
                }
                iframe.setAttribute('style', 'background-color: #fff; position: relative; border: none');
                var chart = doc.querySelector('svg.maidr-frame-svg');
                if (chart) {
                    chart.style.width = '';
                    chart.style.height = '';
                } else {
                    // A chart that takes its frame's width is not made
                    // wider: drawn again under a dialog, a Plotly chart
                    // threw ('mo'). Narrower, it follows the window.
                    iframe.style.maxWidth = width + 'px';
                }
                if (doc.body) doc.body.style.paddingTop = '';
                doc.documentElement.removeAttribute('data-maidr-fit-box');
                doc.documentElement.setAttribute('data-maidr-suspended', '');
                var win = iframe.ownerDocument.defaultView;
                if (win.MutationObserver) {
                    suspended.gone = new win.MutationObserver(function() {
                        if (!iframe.isConnected) maidrSuspendBox(iframe);
                    });
                    suspended.gone.observe(
                        iframe.ownerDocument.body, {childList: true, subtree: true}
                    );
                }
                // The focus coming back to the chart, before the browser
                // scrolls to it.
                suspended.back = function() { maidrSuspendBox(iframe); };
                doc.addEventListener('focusin', suspended.back, true);
            } else {
                var was = iframe.maidrSuspended;
                iframe.maidrSuspended = null;
                if (was.gone) was.gone.disconnect();
                if (doc) doc.removeEventListener('focusin', was.back, true);
                for (var j = 0; j < was.held.length; j++) {
                    var el = was.held[j][0];
                    if (was.held[j][1] === null) el.removeAttribute('style');
                    else el.setAttribute('style', was.held[j][1]);
                    for (var k = 0; k < was.held[j][2].length; k++) {
                        el.classList.add(was.held[j][2][k]);
                    }
                }
                if (was.frame === null) iframe.removeAttribute('style');
                else iframe.setAttribute('style', was.frame);
                iframe.maidrDialogOpen = false;
                if (doc) doc.documentElement.removeAttribute('data-maidr-suspended');
                was.kept();
            }
            return open;
        }
        // Where the page, and every box round the frame that scrolls, are
        // scrolled as a dialog opens, and what puts them back there as it
        // closes, the frame's layout as it was again: scrolled to show the
        // dialog, the page had kept that place, and the browser, giving
        // the chart the focus back, scrolled again to what took it -- for
        // a Plotly chart, a line at its top -- to the window's middle,
        // 185px down, and the reader's highlight half off screen. A chart
        // drawn again, or taken away, under the dialog puts them back too:
        // its output is as it was before the dialog opened. Not once the
        // reader has scrolled, or the window changed size, meanwhile.
        function maidrKeepPlace(iframe) {
            var page = iframe.ownerDocument;
            var win = page.defaultView;
            var kept = [[page.scrollingElement, page.scrollingElement.scrollTop,
                         page.scrollingElement.scrollLeft]];
            for (var el = iframe.parentElement; el; el = el.parentElement) {
                if (el.scrollTop || el.scrollLeft) kept.push([el, el.scrollTop, el.scrollLeft]);
            }
            var moved = false;
            var size = win.innerWidth + 'x' + win.innerHeight;
            var events = ['wheel', 'touchmove', 'keydown'];
            function move() { moved = true; }
            events.forEach(function(type) { win.addEventListener(type, move, true); });
            return function() {
                events.forEach(function(type) { win.removeEventListener(type, move, true); });
                if (moved || win.innerWidth + 'x' + win.innerHeight !== size) return;
                for (var i = 0; i < kept.length; i++) {
                    var to = kept[i];
                    if (to[0].scrollTop !== to[1] || to[0].scrollLeft !== to[2]) {
                        to[0].scrollTo({top: to[1], left: to[2], behavior: 'instant'});
                    }
                }
            };
        }
        // A frame whose height flips between two as a scrollbar comes and
        // goes round it -- the page's, or a box's, coming as the frame grows
        // and going as it shrinks, and the chart fitted to the width it
        // leaves -- keeps the taller of the two: at the classic scrollbars'
        // threshold it was resized without end. That alone: each of the two
        // heights measured at its own width, the box narrower by no more
        // than the scrollbars that came took (maidrBars), whatever their
        // width, the narrower width giving the shorter height, each within
        // a second of the last, the window the same size. The hold lets go
        // as soon as the window changes size, or the box a width other than
        // those two, or the chart a height other than those two: a card
        // taken full screen and back, a window made shorter, a plot drawn
        // again at another size.
        function maidrBars(box) {
            var page = box.ownerDocument;
            var bars = page.defaultView.innerWidth - page.documentElement.clientWidth;
            for (var el = box; el && el !== page.documentElement; el = el.parentElement) {
                // An inline element has no client width, nor scrollbar.
                if (el.clientWidth) bars += el.offsetWidth - el.clientWidth;
            }
            return bars;
        }
        function maidrSteady(iframe, height) {
            var win = iframe.ownerDocument.defaultView;
            var box = iframe.parentElement;
            var width = box ? box.clientWidth : 0;
            var bars = box ? maidrBars(box) : 0;
            var size = win.innerWidth + 'x' + win.innerHeight;
            var flip = iframe.maidrFlip;
            if (!flip || flip.size !== size) {
                flip = iframe.maidrFlip = {size: size, seen: [], hold: 0};
            }
            var seen = flip.seen;
            if (flip.hold) {
                if ((height === seen[0].height || height === seen[1].height)
                        && (width === seen[0].width || width === seen[1].width)) {
                    return flip.hold;
                }
                flip.hold = 0;
                seen.length = 0;
            }
            var now = win.performance.now();
            var last = seen[seen.length - 1];
            if (last && last.height === height) return height;
            seen.push({height: height, width: width, bars: bars, at: now});
            while (seen.length > 3 || now - seen[0].at > 2000) seen.shift();
            if (seen.length === 3) {
                var a = seen[0], b = seen[1], c = seen[2];
                if (c.height === a.height && c.width === a.width
                        && b.width !== a.width && b.bars !== a.bars
                        && Math.abs(b.width - a.width) <= Math.abs(b.bars - a.bars) + 1
                        && (b.width < a.width) === (b.bars > a.bars)
                        && (b.width < a.width) === (b.height < a.height)
                        && c.at - b.at <= 1000 && b.at - a.at <= 1000) {
                    flip.seen = [a, b];
                    flip.hold = Math.max(a.height, b.height);
                    return flip.hold;
                }
            }
            return height;
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

    // The rest of frame.css, which the frame's document starts without:
    // focus rings, a dialog's band, a fitted chart's centring.
    function maidrFrameStyle(frame) {
        var doc = frame.contentWindow && frame.contentWindow.document;
        if (!doc || doc.getElementById('maidr-frame-style')) return;
        var style = doc.createElement('style');
        style.id = 'maidr-frame-style';
        style.textContent = "html[data-maidr-fit-box] figure[id^=maidr-figure-]>div[tabindex]{margin-left:auto;margin-right:auto}figure[id^=maidr-figure]>div[tabindex=\"0\"]:focus{outline:3px solid #1a5fb4 !important;outline-offset:-3px !important}figure[id^=maidr-figure]>div[tabindex=\"0\"]:focus svg.maidr-frame-svg{outline:2px solid #ffffff !important;outline-offset:-5px !important}.js-plotly-plot .svg-container:focus-within{outline:none !important}.js-plotly-plot .svg-container:focus-within::after{content:\"\";position:absolute;inset:0;border:3px solid #1a5fb4;pointer-events:none;z-index:1000}figure[id^=maidr-figure]>div[tabindex=\"0\"]:focus [id^=maidr-bokeh-][id$=-plot]::after{content:\"\";position:absolute;inset:0;border:3px solid #1a5fb4;pointer-events:none;z-index:1000}figure[id^=maidr-figure]>div[tabindex=\"0\"]:focus:has([id^=maidr-bokeh-][id$=-plot]){outline:none !important}textarea:focus,input:focus,select:focus,button:focus-visible,a:focus-visible,[role=button]:focus-visible{outline:3px solid #1a5fb4 !important;outline-offset:-3px !important}@media (forced-colors:active){figure[id^=maidr-figure]>div[tabindex=\"0\"]:focus,textarea:focus,input:focus,select:focus,button:focus-visible,a:focus-visible,[role=button]:focus-visible{outline-color:Highlight !important}figure[id^=maidr-figure]>div[tabindex=\"0\"]:focus svg.maidr-frame-svg{outline:none !important}.js-plotly-plot .svg-container:focus-within::after,figure[id^=maidr-figure]>div[tabindex=\"0\"]:focus [id^=maidr-bokeh-][id$=-plot]::after{border-color:Highlight}}html[data-maidr-dialog-room] .MuiDialog-container{height:var(--maidr-dialog-room) !important;margin-top:calc((100vh - var(--maidr-dialog-room)) / 2) !important}html[data-maidr-dialog-room] .MuiDialog-paper{max-height:calc(var(--maidr-dialog-room) - 64px) !important}";
        (doc.head || doc.documentElement).appendChild(style);
    }
    function matplotlibFrame(frame, options) {
        maidrFrameStyle(frame);

        function resizeIframe() {
            let iframe = frame;
            // Fitted to its box, or, while a dialog is open, laid out as
            // a notebook's frame is (maidrSuspendBox).
            let fitted = !maidrSuspendBox(iframe);
            let fitsOutput = true;
            if (fitsOutput && maidrNotLaidOut(iframe)) return;
            if (
                iframe && iframe.contentWindow &&
                iframe.contentWindow.document &&
                iframe.contentWindow.document.body
            ) {
                let iframeDocument = iframe.contentWindow.document;
                let body = iframeDocument.body;
                let de = iframeDocument.documentElement;
                let letGo = fitted ? maidrHoldStill(iframe) : null;
                let restoreScroll = fitted
                    ? maidrKeepBoxScroll(iframe) : maidrKeepScroll(iframe);
                let before = iframe.style.height;
                let room = fitted ? 0 : maidrDialogRoom(iframeDocument, iframe);

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
                    if (fitted) {
                        // In a Shiny app, the chart is fitted to its box
                        // when the box has a height of its own, and is then
                        // as wide as the box.
                        iframe.style.width = maidrOutputWidth(iframe, true);
                        let boxRoom = maidrBoxRoom(iframe);
                        maidrFitChart(
                            iframeDocument, chart, boxRoom, maidrBoxWidth(iframe), iframe
                        );
                        iframe.style.maxWidth = boxRoom > 0 ? '' : (own + side) + 'px';
                    } else {
                    // While a dialog of maidr's is open, the frame
                    // may be as wide as MUI makes a dialog (600px, and 32px
                    // either side), so that a small chart's frame does not
                    // squeeze it.
                    let dialogOpen = iframeDocument.querySelector('.MuiDialog-root');
                    iframe.style.width = maidrOutputWidth(iframe, false);
                    iframe.style.maxWidth = Math.max(own + side, dialogOpen ? 664 : 0) + 'px';
                    }
                } else if (fitsOutput) {
                    // Until maidr.js has put the chart back: narrowed to
                    // nothing, the frame had no width to measure it at.
                    iframe.style.width = maidrOutputWidth(iframe, fitted);
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
                if (fitted) height = maidrSteady(iframe, height);
                iframe.style.height = (height) + 'px';
                if (restoreScroll) restoreScroll();
                if (letGo) letGo();
                if (fitted && own > 0) maidrRedrawn(iframe);
                if (fitsOutput) {
                    let resized = iframe.style.height !== before;
                    maidrShowDialog(iframeDocument, iframe, room, resized);
                    maidrShowField(iframeDocument, resized);
                }
                if (fitted) maidrShowText(iframeDocument, iframe);
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
        maidrFrameStyle(frame);

        function resizeIframe() {
            var iframe = frame;
            if (!iframe || !iframe.contentWindow || !iframe.contentWindow.document) {
                return;
            }
            // Fitted to its box, or, while a dialog is open, laid out as
            // a notebook's frame is (maidrSuspendBox).
            var fitted = !maidrSuspendBox(iframe);
            var fitsOutput = true;
            var keepsPadding = true;
            var widens = options.widens;

            if (fitsOutput && maidrNotLaidOut(iframe)) return;
            var doc = iframe.contentWindow.document;
            var body = doc.body;
            if (!body) return;
            var de = doc.documentElement;
            var letGo = fitted ? maidrHoldStill(iframe) : null;
            var restoreScroll = fitted
                ? maidrKeepBoxScroll(iframe) : maidrKeepScroll(iframe);
            var before = iframe.style.height;
            var room = fitted ? 0 : maidrDialogRoom(doc, iframe);
            // In a Shiny app: the room the box gives the chart (none when
            // the box takes its height from the frame), and a chart that
            // takes its height from its container as tall as that room
            // less the line kept for maidr's text, or, with none,
            // options.fillHeight; see _BOX_JS. While a dialog is open, it
            // is left at the height it has: drawn again under a dialog, a
            // Plotly chart threw ('mo') and lost its highlight.
            if (fitted) {
                var boxRoom = maidrBoxRoom(iframe);
                maidrKeepGutter(iframe, boxRoom > 0 && !widens);
                if (options.fillHeight) {
                    maidrFillHeight(doc, boxRoom > 0
                        ? boxRoom - maidrTextLine(doc)
                        : options.fillHeight, function() {
                            requestAnimationFrame(resizeIframe);
                        }, options.keepsShape);
                }
            }

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
                // Not while a dialog is open: MUI centres it in the frame,
                // which is then as wide as the page shows.
                if (fitted && widens && de.scrollWidth > iframe.contentWindow.innerWidth + 1) {
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
            if (fitted) height = maidrSteady(iframe, height);

            iframe.style.height = height + 'px';
            if (restoreScroll) restoreScroll();
            if (letGo) letGo();
            if (doc.querySelector('[role=img], [role=application]')) {
                maidrRedrawn(iframe);
            }
            if (fitsOutput) {
                var resized = iframe.style.height !== before;
                maidrShowDialog(doc, iframe, room, resized);
                maidrShowField(doc, resized);
            }
            if (fitted) maidrShowText(doc, iframe);
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
    if (!kinds.matplotlib) kinds.matplotlib = matplotlibFrame;
    if (!kinds.plotly) kinds.plotly = plotlyFrame;
    if (window.maidrShinyFrame) return;
    window.maidrShinyFrame = function (frame, kind, options) {
        kinds[kind](frame, options || {});
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
