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
                    if (el.scrollTop === top && el.scrollLeft === kept[i][2]) continue;
                    // At once: a page whose scroll-behavior is smooth
                    // (Bootstrap's, so every Shiny app's) scrolled back
                    // over a third of a second, and was stopped short by
                    // the next measure.
                    el.scrollTo({top: top, left: kept[i][2], behavior: 'instant'});
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
                // the reader's view shows it whole. At once, whatever the
                // page's scroll-behavior: Bootstrap's is smooth, and the
                // frame measured again while it scrolled stopped it short
                // (a Shiny app's settings dialog lost its Close button).
                iframe.scrollIntoView(
                    {block: 'center', inline: 'nearest', behavior: 'instant'}
                );
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
        // The box's room, measured unless a dialog of maidr's holds the box
        // taller, and the room the dialog gets: what the reader sees of the
        // window, or of a container of a height of its own that clips the
        // output (a fillable card's body), never less than the box's own.
        function maidrBox(iframe, doc) {
            var open = !!doc.querySelector('.MuiDialog-root');
            if (!open || iframe.maidrBoxRoom === undefined) {
                maidrHoldBox(iframe, 0);
                iframe.maidrBoxRoom = maidrBoxRoom(iframe);
            }
            var room = iframe.maidrBoxRoom;
            var dialog = open ? maidrBoxDialogRoom(iframe, room) : 0;
            maidrHoldBox(iframe, room > 0 ? dialog : 0);
            return {room: room, dialog: dialog};
        }
        // The box is held at the window's room first. A container that
        // clips the output but grows with its content -- a card's body in a
        // page that is not fillable, every card on a phone -- grows with it
        // and is no limit: capping the room at its height capped it at the
        // chart's own, and a help dialog in a 300px output showed 104px of
        // its text. One whose height is its own -- a fillable card's body,
        // a sidebar layout's main area, a card given a height -- is then
        // overflowed, and the room is what it shows.
        function maidrBoxDialogRoom(iframe, own) {
            var page = iframe.ownerDocument;
            var win = page.defaultView;
            var room = win.innerHeight || 0;
            if (win !== win.top) room = Math.max(room, 480);
            room = Math.max(room, own);
            maidrHoldBox(iframe, Math.floor(room));
            var box = iframe.parentElement;
            for (var el = box && box.parentElement; el && el !== page.body;
                    el = el.parentElement) {
                var style = win.getComputedStyle(el);
                if (style.overflowY === 'visible' || style.display === 'contents'
                        || el.scrollHeight <= el.clientHeight + 1) {
                    continue;
                }
                room = Math.min(room, el.clientHeight
                    - (parseFloat(style.paddingTop) || 0)
                    - (parseFloat(style.paddingBottom) || 0));
            }
            return Math.floor(Math.max(room, own));
        }
        // The box, and the output it fills, at least this tall; 0 gives
        // them back the height they had.
        function maidrHoldBox(iframe, room) {
            var box = iframe.parentElement;
            var held = [box, box && box.parentElement];
            for (var i = 0; i < held.length; i++) {
                var el = held[i];
                if (!el) continue;
                if (room > 0) {
                    if (el.maidrHeld === undefined) el.maidrHeld = el.style.minHeight;
                    if (el.style.minHeight !== room + 'px') el.style.minHeight = room + 'px';
                } else if (el.maidrHeld !== undefined) {
                    el.style.minHeight = el.maidrHeld;
                    el.maidrHeld = undefined;
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
        // scaled to it -- given this height. plotly.js draws it again at
        // that height later, after a debounce: the frame was measured
        // before it had, and kept the old plot's height until something
        // else measured it -- full screen left a Plotly chart's text below
        // its frame, out of sight. ``redrawn`` measures it once plotly.js
        // has drawn it; the height is then the one set, so that measuring
        // resizes nothing.
        function maidrFillHeight(doc, height, redrawn, keepsShape) {
            var plot = doc.querySelector(
                '.js-plotly-plot, [id^="maidr-bokeh-"][id$="-plot"]'
            );
            if (!plot) return;
            height = Math.max(Math.floor(height), 96);
            if (keepsShape) height = maidrKeepShape(plot, height);
            var px = height + 'px';
            if (plot.style.height === px) return;
            plot.style.height = px;
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
            let fitsOutput = true;
            let keepsPadding = true;
            let fitsBox = true;
            let iframe = frame;
            if (fitsOutput && maidrNotLaidOut(iframe)) return;
            if (
                iframe && iframe.contentWindow &&
                iframe.contentWindow.document &&
                iframe.contentWindow.document.body
            ) {
                let iframeDocument = iframe.contentWindow.document;
                let body = iframeDocument.body;
                let de = iframeDocument.documentElement;
                let restoreScroll = fitsOutput ? maidrKeepScroll(iframe) : null;
                let before = iframe.style.height;
                let room = fitsOutput ? maidrDialogRoom(iframeDocument, iframe) : 0;

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
                // In a Shiny app, the height of the box the frame is shown
                // in, when it has one of its own: the chart is fitted to it.
                let boxRoom = 0;
                if (own > 0) {
                    // While a dialog of maidr's is open, the frame
                    // may be as wide as MUI makes a dialog (600px, and 32px
                    // either side), so that a small chart's frame does not
                    // squeeze it.
                    let dialogOpen = iframeDocument.querySelector('.MuiDialog-root');
                    iframe.style.width = maidrOutputWidth(iframe, keepsPadding);
                    if (fitsBox) {
                        let fit = maidrBox(iframe, iframeDocument);
                        boxRoom = fit.room;
                        room = fit.dialog;
                        maidrFitChart(
                            iframeDocument, chart, boxRoom, maidrBoxWidth(iframe), iframe
                        );
                    }
                    // A chart fitted to its box is as wide as the box.
                    iframe.style.maxWidth = boxRoom > 0
                        ? ''
                        : Math.max(own + side, dialogOpen ? 664 : 0) + 'px';
                } else if (fitsOutput) {
                    // Until maidr.js has put the chart back: narrowed to
                    // nothing, the frame had no width to measure it at.
                    iframe.style.width = maidrOutputWidth(iframe, keepsPadding);
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
                if (fitsOutput) {
                    let resized = iframe.style.height !== before;
                    maidrShowDialog(iframeDocument, iframe, room, resized);
                    maidrShowField(iframeDocument, resized);
                }
                if (fitsBox) maidrShowText(iframeDocument, iframe);
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
            var fitsOutput = true;
            var keepsPadding = true;
            var widens = options.widens;
            var iframe = frame;
            if (!iframe || !iframe.contentWindow || !iframe.contentWindow.document) {
                return;
            }

            if (fitsOutput && maidrNotLaidOut(iframe)) return;
            var doc = iframe.contentWindow.document;
            var body = doc.body;
            if (!body) return;
            var de = doc.documentElement;
            var restoreScroll = fitsOutput ? maidrKeepScroll(iframe) : null;
            var before = iframe.style.height;
            var room = fitsOutput ? maidrDialogRoom(doc, iframe) : 0;

            var fit = maidrBox(iframe, doc);
            room = fit.dialog;
            if (options.fillHeight) {
                maidrFillHeight(doc, fit.room > 0
                    ? fit.room - maidrTextLine(doc)
                    : options.fillHeight, function() {
                        requestAnimationFrame(resizeIframe);
                    }, options.keepsShape);
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
            if (fitsOutput) {
                var resized = iframe.style.height !== before;
                maidrShowDialog(doc, iframe, room, resized);
                maidrShowField(doc, resized);
            }
            maidrShowText(doc, iframe);
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
})();
