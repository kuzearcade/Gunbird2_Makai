// Pre-script: Gunbird 2 (PS5, SH-2 BE) memory map.
// Boot copies: ROM 0x780 (0x2DCDC bytes) -> 0x06000000 (P), ROM 0x2E47C (0x4A61) -> 0x0602DCDC (D),
// BSS 0x06040000-0x06079F90, data ROM (512K) -> 0x06080000. Stack top 0x06080000.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.nio.file.*;

public class SetupArcade extends GhidraScript {
    MemoryBlock blk(String n, long a, byte[] src, int off, int len) throws Exception {
        AddressSpace sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
        return currentProgram.getMemory().createInitializedBlock(n, sp.getAddress(a),
            new ByteArrayInputStream(src, off, len), len, monitor, false);
    }
    @Override
    public void run() throws Exception {
        setAnalysisOption(currentProgram, "Aggressive Instruction Finder", "true");
        Memory mem = currentProgram.getMemory();
        AddressSpace sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
        String root = System.getenv("GB2ROOT");
        byte[] rom = Files.readAllBytes(Paths.get(root + "/assets/arcade/prog_be.bin"));
        byte[] pd = Files.readAllBytes(Paths.get(root + "/assets/arcade/pdata_be.bin"));
        blk("DATAROM", 0x05000000L, pd, 0, pd.length);
        blk("RAM_P", 0x06000000L, rom, 0x780, 0x2DCDC).setWrite(true);
        blk("RAM_D", 0x0602DCDCL, rom, 0x2E47C, 0x4A61).setWrite(true);
        mem.createUninitializedBlock("RAM_FREE", sp.getAddress(0x0603273DL), 0x06040000L - 0x0603273DL, false).setWrite(true);
        mem.createUninitializedBlock("RAM_BSS", sp.getAddress(0x06040000L), 0x40000, false).setWrite(true);
        blk("RAM_DATA", 0x06080000L, pd, 0, pd.length).setWrite(true);
        mem.createUninitializedBlock("IO", sp.getAddress(0x03000000L), 0x8, false).setVolatile(true);
        mem.createUninitializedBlock("YMF", sp.getAddress(0x03100000L), 0x8, false).setVolatile(true);
        MemoryBlock v = mem.createUninitializedBlock("VIDEO", sp.getAddress(0x04000000L), 0x80000, false);
        v.setWrite(true); v.setVolatile(true);
        mem.createUninitializedBlock("ONCHIP", sp.getAddress(0xFFFFFE00L), 0x200, false).setVolatile(true);
        for (int i = 0; i < 256; i++) {
            createDWord(sp.getAddress(i * 4L));
            if (i == 1 || i == 3) continue;
            long t = mem.getInt(sp.getAddress(i * 4L)) & 0xffffffffL;
            boolean ok = (t >= 0x400 && t < 0x100000) || (t >= 0x06000000L && t < 0x0602DCDCL);
            if (ok && (t & 1) == 0) {
                Address a = sp.getAddress(t);
                createFunction(a, null);
                currentProgram.getSymbolTable().createLabel(a, String.format("vec_%02x_%x", i, t), SourceType.USER_DEFINED);
            }
        }
    }
}
