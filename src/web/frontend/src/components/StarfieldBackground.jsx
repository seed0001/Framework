import React, { useEffect, useRef } from 'react';

export default function StarfieldBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let W, H, stars = [], nebula = [];
    let animationFrameId;

    function resize() {
      W = canvas.width = window.innerWidth;
      H = canvas.height = window.innerHeight;
    }

    resize();
    window.addEventListener('resize', resize);

    function mkStars() {
      stars = [];
      const n = Math.min(220, Math.floor((W * H) / 6000));
      for (let i = 0; i < n; i++) {
        stars.push({
          x: Math.random() * W,
          y: Math.random() * H,
          r: Math.random() * 1.4 + 0.2,
          a: Math.random() * 0.7 + 0.1,
          drift: (Math.random() - 0.5) * 0.015,
          twinkleSpeed: Math.random() * 0.012 + 0.004,
          twinklePhase: Math.random() * Math.PI * 2,
        });
      }
      nebula = [];
      const nc = 4;
      for (let i = 0; i < nc; i++) {
        nebula.push({
          x: Math.random() * W,
          y: Math.random() * H,
          r: Math.random() * 80 + 40,
          color: ['rgba(0,212,255,', 'rgba(168,85,247,', 'rgba(34,211,160,'][i % 3],
          a: Math.random() * 0.04 + 0.01,
        });
      }
    }

    mkStars();
    window.addEventListener('resize', mkStars);

    let frame = 0;
    function draw() {
      ctx.clearRect(0, 0, W, H);

      // Draw nebula blobs
      for (const nb of nebula) {
        const grad = ctx.createRadialGradient(nb.x, nb.y, 0, nb.x, nb.y, nb.r);
        grad.addColorStop(0, nb.color + nb.a + ')');
        grad.addColorStop(1, nb.color + '0)');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(nb.x, nb.y, nb.r, 0, Math.PI * 2);
        ctx.fill();
      }

      // Draw stars
      for (const s of stars) {
        const twinkle = 0.5 + 0.5 * Math.sin(frame * s.twinkleSpeed + s.twinklePhase);
        ctx.globalAlpha = s.a * twinkle;
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fill();
        s.x += s.drift;
        if (s.x < -2) s.x = W + 2;
        if (s.x > W + 2) s.x = -2;
      }
      ctx.globalAlpha = 1;
      frame++;
      animationFrameId = requestAnimationFrame(draw);
    }

    draw();

    return () => {
      window.removeEventListener('resize', resize);
      window.removeEventListener('resize', mkStars);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 0,
        opacity: 0.55,
      }}
    />
  );
}
