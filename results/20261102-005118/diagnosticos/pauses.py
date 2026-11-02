import re
# Janela medida: de 30s de carga em diante; o log traz tempo desde o início do processo.
for name,f in [('native-1000 1g','results/diagnostico-gc/logs/java-native-1000-1.log'),('native-5000 1g','results/diagnostico-gc/logs/java-native-5000-1.log'),('native-5000 2g','results/diagnostico-native-2g/logs/java-native-5000-1.log'),('jvm-5000 1g','results/diagnostico-gc/logs/java-jvm-5000-1.log')]:
    ev=[]
    for l in open(f,errors='replace'):
        m=re.match(r'\[([\d.]+)s\].*(Pause \S+.*?) ([\d.]+)ms',l)
        if m: ev.append((float(m[1]),m[2],float(m[3])))
    last=ev[-1][0]; w=[e for e in ev if e[0]>=last-60]
    tot=sum(e[2] for e in w); full=[e for e in w if 'Full' in e[1]]
    print(f"{name}: pausas(60s finais)={len(w)} total={tot/1000:.1f}s ({tot/600:.1f}%) maior={max(e[2] for e in w):.0f}ms full={len(full)} mediana={sorted(e[2] for e in w)[len(w)//2]:.0f}ms")
