"""
GEOTracer Advanced Tracing Module
Улучшенная трассировка со статистикой как у PingPlotter
"""

import asyncio
import socket
import struct
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import statistics


@dataclass
class HopStats:
    """Статистика для одного хопа"""
    hop: int
    ip: str = ""
    rtts: List[float] = field(default_factory=list)
    losses: int = 0
    total_probes: int = 0
    
    @property
    def min_rtt(self) -> Optional[float]:
        return min(self.rtts) if self.rtts else None
    
    @property
    def avg_rtt(self) -> Optional[float]:
        return statistics.mean(self.rtts) if self.rtts else None
    
    @property
    def max_rtt(self) -> Optional[float]:
        return max(self.rtts) if self.rtts else None
    
    @property
    def jitter(self) -> Optional[float]:
        """Jitter как среднее отклонение между последовательными RTT"""
        if len(self.rtts) < 2:
            return None
        diffs = [abs(self.rtts[i] - self.rtts[i-1]) for i in range(1, len(self.rtts))]
        return statistics.mean(diffs) if diffs else None
    
    @property
    def loss_percent(self) -> float:
        if self.total_probes == 0:
            return 0.0
        return (self.losses / self.total_probes) * 100
    
    @property
    def is_hidden(self) -> bool:
        """Хоп считается скрытым, если есть потери но есть ответы"""
        return self.total_probes > 0 and self.losses > 0 and len(self.rtts) > 0


class AdvancedTracer:
    """
    Продвинутый трассировщик с многократными зондами и статистикой
    """
    
    DEFAULT_PROBES = 20  # Количество зондов на хоп (как у PingPlotter ~23)
    DEFAULT_TIMEOUT = 2.0  # Таймаут в секундах
    DEFAULT_TTL_MAX = 30
    DEFAULT_INTERVAL = 0.1  # Интервал между зондами (сек)
    
    def __init__(self, target: str, probes: int = DEFAULT_PROBES, 
                 timeout: float = DEFAULT_TIMEOUT, max_ttl: int = DEFAULT_TTL_MAX):
        self.target = target
        self.probes = probes
        self.timeout = timeout
        self.max_ttl = max_ttl
        self.hops: Dict[int, HopStats] = {}
        self.target_ip: Optional[str] = None
        
    def _create_icmp_packet(self, icmp_id: int, seq: int, data: bytes = b"") -> bytes:
        """Создание ICMP Echo Request пакета"""
        icmp_type = 8  # Echo Request
        icmp_code = 0
        checksum = 0
        header = struct.pack("!BBHHH", icmp_type, icmp_code, checksum, icmp_id, seq)
        packet = header + data
        # Пересчет checksum
        checksum = self._checksum(packet)
        header = struct.pack("!BBHHH", icmp_type, icmp_code, checksum, icmp_id, seq)
        return header + data
    
    def _checksum(self, data: bytes) -> int:
        """Расчет контрольной суммы ICMP"""
        if len(data) % 2:
            data += b"\x00"
        s = sum(struct.unpack("!" + "H" * (len(data) // 2), data))
        while s >> 16:
            s = (s & 0xFFFF) + (s >> 16)
        return ~s & 0xFFFF
    
    async def _send_probe(self, ttl: int, probe_id: int) -> Tuple[Optional[str], Optional[float]]:
        """Отправка одного зонда и получение ответа"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            sock.setsockopt(socket.SOL_IP, socket.IP_TTL, ttl)
            sock.settimeout(self.timeout)
            
            packet = self._create_icmp_packet(probe_id, ttl)
            start_time = time.time()
            sock.sendto(packet, (self.target, 0))
            
            try:
                while True:
                    elapsed = time.time() - start_time
                    if elapsed > self.timeout:
                        return None, None
                    
                    remaining = self.timeout - elapsed
                    sock.settimeout(remaining)
                    recv_data, addr = sock.recvfrom(1500)
                    
                    # Парсинг IP заголовка
                    ip_header = recv_data[0:20]
                    ip_ttl = struct.unpack("!B", ip_header[8:9])[0]
                    
                    # Проверка TTL ответа
                    if ip_ttl <= ttl:
                        rtt = (time.time() - start_time) * 1000  # мс
                        return addr[0], rtt
                    
            except socket.timeout:
                return None, None
            finally:
                sock.close()
                
        except PermissionError:
            # Нет прав на raw socket
            return None, None
        except Exception:
            return None, None
    
    async def _trace_hop(self, ttl: int) -> HopStats:
        """Трассировка одного хопа с множественными зондами"""
        stats = HopStats(hop=ttl)
        
        for i in range(self.probes):
            ip, rtt = await self._send_probe(ttl, i)
            stats.total_probes += 1
            
            if ip and rtt is not None:
                if not stats.ip:
                    stats.ip = ip
                elif stats.ip != ip:
                    # Разные IP на одном хопе (ECMP)
                    pass
                stats.rtts.append(rtt)
            else:
                stats.losses += 1
            
            if i < self.probes - 1:
                await asyncio.sleep(self.DEFAULT_INTERVAL)
        
        return stats
    
    async def trace(self) -> List[HopStats]:
        """
        Выполнение полной трассировки со статистикой
        Возвращает список HopStats для каждого хопа
        """
        self.hops = {}
        results = []
        
        # Сначала определяем целевой IP
        try:
            self.target_ip = socket.gethostbyname(self.target)
        except socket.gaierror:
            raise ValueError(f"Не удалось разрешить {self.target}")
        
        # Трассировка по каждому TTL
        for ttl in range(1, self.max_ttl + 1):
            stats = await self._trace_hop(ttl)
            self.hops[ttl] = stats
            results.append(stats)
            
            # Если достигли цели - останавливаемся
            if stats.ip == self.target_ip:
                break
            
            # Если все зонды потеряны после 5 хопов - возможный конец
            if ttl > 5 and stats.losses == self.probes:
                # Проверяем следующие 2 хопа для уверенности
                continue_check = True
                for next_ttl in range(ttl + 1, min(ttl + 3, self.max_ttl + 1)):
                    next_stats = await self._trace_hop(next_ttl)
                    self.hops[next_ttl] = next_stats
                    results.append(next_stats)
                    if next_stats.ip:
                        continue_check = False
                        break
                if continue_check:
                    break
        
        return results
    
    def detect_hidden_hops(self) -> List[Tuple[int, int]]:
        """
        Обнаружение скрытых узлов по аномалиям RTT
        Возвращает список кортежей (предполагаемый_хоп, между_хопами)
        """
        hidden = []
        prev_stats = None
        
        for ttl in range(1, len(self.hops) + 1):
            if ttl not in self.hops:
                continue
            
            curr_stats = self.hops[ttl]
            
            if prev_stats and prev_stats.ip and curr_stats.ip:
                # Аномальный скачок RTT может указывать на скрытый узел
                if prev_stats.avg_rtt and curr_stats.avg_rtt:
                    delta = curr_stats.avg_rtt - prev_stats.avg_rtt
                    # Если скачок > 50мс и есть потери - возможен скрытый узел
                    if delta > 50 and (prev_stats.is_hidden or curr_stats.is_hidden):
                        hidden.append((ttl, ttl - 1))
            
            prev_stats = curr_stats
        
        return hidden
    
    def get_summary(self) -> str:
        """Получить сводку в стиле PingPlotter"""
        lines = []
        lines.append(f"Hop  Sent  PL%     Min     Max     Avg  Jitter  Host")
        lines.append("-" * 75)
        
        for ttl in sorted(self.hops.keys()):
            stats = self.hops[ttl]
            min_r = f"{stats.min_rtt:.2f}" if stats.min_rtt else "0"
            max_r = f"{stats.max_rtt:.2f}" if stats.max_rtt else "0"
            avg_r = f"{stats.avg_rtt:.2f}" if stats.avg_rtt else "0"
            jit = f"{stats.jitter:.2f}" if stats.jitter else "0"
            loss = f"{stats.loss_percent:.0f}"
            host = stats.ip if stats.ip else "* * *"
            
            lines.append(f"{ttl:3}  {stats.total_probes:4}  {loss:3}  {min_r:>6}  {max_r:>6}  {avg_r:>6}  {jit:>6}  {host}")
        
        return "\n".join(lines)


async def main():
    """Тестовый запуск"""
    tracer = AdvancedTracer("8.8.8.8", probes=10, timeout=2.0)
    
    print("Запуск улучшенной трассировки...")
    results = await tracer.trace()
    
    print("\n" + "=" * 75)
    print(tracer.get_summary())
    print("=" * 75)
    
    hidden = tracer.detect_hidden_hops()
    if hidden:
        print(f"\nОбнаружено скрытых узлов: {len(hidden)}")
        for h in hidden:
            print(f"  - Между хопами {h[1]} и {h[0]}")


if __name__ == "__main__":
    asyncio.run(main())
