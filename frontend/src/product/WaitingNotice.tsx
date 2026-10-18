import { useEffect, useState } from "react";
import { StatusNotice } from './StatusNotice.tsx';

export function WaitingNotice({ message, stop, title = '正在等待结果' }: { message: string; stop: () => void; title?: string }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = performance.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((performance.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);
  return <div aria-label="本页等待状态">
    <StatusNotice state="waiting" title={title}>{message} 本页已等待 {seconds} 秒。</StatusNotice>
    <button onClick={stop}>停止本页等待</button>
    <p>服务端任务可能继续处理。停止后可按原操作身份只读查询结果。</p>
  </div>;
}
