// Make [start,end) read-only (splitting blocks as needed) so the decompiler folds literal-pool constants.
// args: start end [start end ...] (hex)
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.mem.*;
public class SetRO extends GhidraScript {
    public void run() throws Exception {
        String[] a = getScriptArgs();
        AddressSpace sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
        Memory mem = currentProgram.getMemory();
        for (int i = 0; i + 1 < a.length; i += 2) {
            Address s = sp.getAddress(Long.parseLong(a[i], 16)), e = sp.getAddress(Long.parseLong(a[i + 1], 16));
            MemoryBlock b = mem.getBlock(s);
            if (!b.getStart().equals(s)) { mem.split(b, s); b = mem.getBlock(s); }
            if (b.getEnd().compareTo(e) >= 0 && !b.getEnd().equals(e.subtract(1))) mem.split(b, e);
            b = mem.getBlock(s);
            b.setWrite(false);
            println("RO " + b.getName() + " " + b.getStart() + "-" + b.getEnd());
        }
    }
}
