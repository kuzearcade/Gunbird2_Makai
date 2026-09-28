// Apply "hexaddr name" lines from a file as function names (or labels if no function)
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.nio.file.*;
public class ApplySymbols extends GhidraScript {
    public void run() throws Exception {
        AddressSpace sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
        int n = 0;
        for (String l : Files.readAllLines(Paths.get(getScriptArgs()[0]))) {
            l = l.trim(); if (l.isEmpty() || l.startsWith("#")) continue;
            String[] p = l.split("\\s+");
            Address a = sp.getAddress(Long.parseLong(p[0], 16));
            Function f = getFunctionAt(a);
            boolean isFn = p.length < 3 || !p[2].equals("label");
            if (f == null && isFn && currentProgram.getMemory().getBlock(a) != null
                    && currentProgram.getMemory().getBlock(a).isExecute()) {
                Function nx = getFunctionAfter(a);
                if (nx != null && nx.getEntryPoint().subtract(a) < 0x20 && nx.getEntryPoint().subtract(a) > 0
                        && getFunctionContaining(a) == null)
                    removeFunction(nx);
                disassemble(a);
                f = createFunction(a, null);
            }
            if (f != null) f.setName(p[1], SourceType.USER_DEFINED);
            else currentProgram.getSymbolTable().createLabel(a, p[1], SourceType.USER_DEFINED);
            n++;
        }
        println("applied " + n);
    }
}
